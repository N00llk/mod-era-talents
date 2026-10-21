#ifndef MOD_ERA_BOT_BUILD_SELECTION_H
#define MOD_ERA_BOT_BUILD_SELECTION_H

#include <array>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

namespace EraBotBuildSelection
{
    inline std::string Trim(std::string const& value)
    {
        auto first = value.find_first_not_of(" \t\r\n");
        return first == std::string::npos ? "" : value.substr(first, value.find_last_not_of(" \t\r\n") - first + 1);
    }

    inline std::string Lower(std::string value)
    {
        for (char& ch : value)
            ch = char(std::tolower(static_cast<unsigned char>(ch)));
        return value;
    }

    // Playerbots' encoded talent links contain up to three digit strings. Validate before
    // its permissive parser turns arbitrary characters into unsigned rank counts.
    inline bool ValidLink(std::string const& link)
    {
        if (link.empty() || link.size() > 122)
            return false;
        unsigned separators = 0, points = 0, length = 0;
        for (char ch : link)
        {
            if (ch == '-')
            {
                if (++separators > 2)
                    return false;
                length = 0;
            }
            else
            {
                if (ch < '0' || ch > '5' || ++length > 40)
                    return false;
                points += unsigned(ch - '0');
            }
        }
        return points > 0 && points <= 71;
    }

    // Select by POINTS, independent of the native parser's ordering by node count.
    // A tied or empty template cannot identify a unique requested specialization.
    inline int PrimaryTab(std::vector<std::vector<std::uint32_t>> const& parsed)
    {
        std::array<unsigned, 3> points = {};
        for (auto const& entry : parsed)
        {
            if (entry.size() != 4 || entry[0] >= 3 || entry[3] == 0 || entry[3] > 5)
                return -1;
            points[entry[0]] += entry[3];
        }
        int best = 0;
        for (int tab = 1; tab < 3; ++tab)
            if (points[tab] > points[best])
                best = tab;
        if (!points[best] || points[0] + points[1] + points[2] > 71)
            return -1;
        for (int tab = 0; tab < 3; ++tab)
            if (tab != best && points[tab] == points[best])
                return -1;
        return best;
    }
}

#endif
