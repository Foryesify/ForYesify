// Simple program: appends two hosts entries and flushes DNS
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>

int main()
{
    auto HOSTS_PATH = "C:\\Windows\\System32\\drivers\\etc\\hosts";
    auto lines = {
        "1.2.3.4 www.bilibili.com",
        "1.2.3.4 www.douyin.com",
        "1.2.3.4 www.kuaishou.com",
        "1.2.3.4 www.kuaishou.cn"};
    std::string content;
        std::ifstream in(HOSTS_PATH);
        if (!in)
        {
            std::cerr << "Cannot open hosts file (run as admin)\n";
            system("pause");
            return 1;
        }
        std::ostringstream ss;
        ss << in.rdbuf();
        content = ss.str();

    auto changed = false;
    for (auto &ln : lines)
    {
        if (content.find(ln) == std::string::npos)
        {
            std::ofstream out(HOSTS_PATH, std::ios::app);
            if (!out)
            {
                std::cerr << "Cannot write to hosts file (permission)\n";
                system("pause");
                return 2;
            }
            out << ln << "\r\n";
            changed = true;
        }
    }
    system("ipconfig /flushdns");
    return 0;
}
