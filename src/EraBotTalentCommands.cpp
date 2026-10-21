#include "EraTalentBots.h"

#ifdef MOD_PLAYERBOTS
#include "EraBotBuildSelection.h"
#include "EraTalentContent.h"
#include "EraTalents.h"
#include "EraTalentsConfig.h"
#include "AiFactory.h"
#include "DBCStores.h"
#include "Player.h"
#include "Playerbots.h"
#include "PlayerbotAI.h"
#include "PlayerbotAIConfig.h"
#include "PlayerbotFactory.h"
#include "RandomPlayerbotMgr.h"
#include "SpellMgr.h"
#include <sstream>

namespace
{
    using EraBotBuildSelection::Lower;
    using EraBotBuildSelection::Trim;

    int BuildForTemplate(Player* bot, std::vector<std::vector<uint32>> const& parsed)
    {
        int tab = EraBotBuildSelection::PrimaryTab(parsed);
        if (tab != 1 || bot->getClass() != CLASS_DRUID)
            return tab;
        // Match the factory's feral discriminator: Thick Hide selects bear; its absence cat.
        for (uint32 id = 0; id < sTalentStore.GetNumRows(); ++id)
        {
            TalentEntry const* talent = sTalentStore.LookupEntry(id);
            if (!talent)
                continue;
            bool thickHide = false;
            for (uint32 spell : talent->RankID)
                thickHide |= spell == 16931;
            if (!thickHide)
                continue;
            for (auto const& entry : parsed)
                if (entry[0] == 1 && entry[1] == talent->Row && entry[2] == talent->Col)
                    return 1;
        }
        return 3;
    }

    std::string Help()
    {
        return "Talents usage: talents spec list, talents spec <specName>, talents apply <link>, talents autopick. "
               "Names and encoded talent links select a specialization; its build follows my current era. "
               "Era talents have one build per era.";
    }

    bool ApplyBuild(Player* bot, int tab, std::string const& source, std::string& response)
    {
        EraId era = EraTalentBots::BotEra(bot);
        char const* eraName = era == ERA_VANILLA ? "Vanilla" : "TBC";
        if (tab < 0 || tab > 3 || (tab == 3 && bot->getClass() != CLASS_DRUID))
        {
            response = "Cannot identify a unique specialization from this build. My talents were unchanged.";
            return false;
        }
        if (bot->GetLevel() < 10 || !bot->IsAlive() || bot->IsInCombat() || !bot->IsInWorld())
        {
            response = "I must be alive, out of combat, and level 10 or higher to change talents.";
            return false;
        }
        // Check the loaded data before resetting a working build. A missing SQL import must
        // produce an error instead of replacing the current build with an incomplete one.
        auto nodes = sEraTalentContent->NodesFor(uint8(era), bot->getClass());
        for (EraTalentNode const* node : nodes)
        {
            if (node->rankSpell.size() != node->maxRank)
            {
                response = "Era talent data is incomplete; my talents were unchanged.";
                return false;
            }
            for (uint32 spell : node->rankSpell)
                if (!spell || !sSpellMgr->GetSpellInfo(spell))
                {
                    response = "Era talent spells are missing; my talents were unchanged.";
                    return false;
                }
        }
        if (!EraTalentBots::FactoryReconcile(bot, tab))
        {
            response = "This era build is unavailable.";
            return false;
        }
        PlayerbotFactory factory(bot, bot->GetLevel());
        factory.InitAvailableSpells();
        EraTalentBots_PostTrainerWalk(bot);
        EraTalentBots::InvalidateSpecCache(bot);
        if (bot->getClass() == CLASS_SHAMAN && EraTalentBots_ResolveSpellId(bot, 30798))
        {
            bot->SetSkill(SKILL_DUAL_WIELD, 0, 1, 1);
            bot->SetCanDualWield(true);
        }
        GET_PLAYERBOT_AI(bot)->ResetStrategies();
        std::ostringstream out;
        out << "Applied " << eraName << " " << source << " era build ("
            << EraTalents::SpentPoints(bot, era) << " points).";
        if (EraTalents::AvailablePoints(bot, era))
            out << " Some points could not be spent; check the server's era talent data.";
        response = out.str();
        return true;
    }
}

// Called after playerbots' own command parsing and permission checks. True means handled,
// including errors; returning false leaves the entire native WotLK command path untouched.
bool EraTalentBots_HandleTalentCommand(Player* bot, std::string const& param, std::string& response)
{
    if (!sEraTalentsConfig->BotTalents() || !EraTalentBots::IsBot(bot) ||
        !EraTalentBots::IsEraManaged(bot) || !GET_PLAYERBOT_AI(bot) ||
        sEraTalentContent->NodesFor(uint8(EraTalentBots::BotEra(bot)), bot->getClass()).empty())
        return false;

    std::string command = Trim(param);
    std::string lower = Lower(command);
    uint32 cls = bot->getClass();
    char const* eraName = EraTalentBots::BotEra(bot) == ERA_VANILLA ? "Vanilla" : "TBC";
    if (command.empty() || lower == "help")
    {
        uint32 tabs[3] = {};
        EraTalentBots_SpecTabs(bot, tabs);
        std::ostringstream out;
        out << "My " << eraName << " talents: " << tabs[0] << "/" << tabs[1] << "/" << tabs[2] << ". " << Help();
        response = out.str();
    }
    else if (lower == "spec list")
    {
        std::ostringstream out;
        out << eraName << " builds (preset names select the era specialization):";
        for (int spec = 0; spec < MAX_SPECNO; ++spec)
        {
            std::string const& name = sPlayerbotAIConfig.PremadeSpecName[cls][spec];
            if (name.empty())
                continue;
            int tab = BuildForTemplate(bot, sPlayerbotAIConfig.ParsedSpecLinkOrder[cls][spec][80]);
            if (tab >= 0)
                out << "\n" << name << " -> tree " << (tab == 3 ? 2 : tab + 1)
                    << (cls == CLASS_DRUID && tab == 1 ? " (bear)" : tab == 3 ? " (cat)" : "");
        }
        response = out.str();
    }
    else if (lower.compare(0, 5, "spec ") == 0)
    {
        std::string name = Trim(command.substr(5));
        response = "Spec " + name + " not found. Use talents spec list.";
        for (int spec = 0; spec < MAX_SPECNO; ++spec)
        {
            std::string const& configured = sPlayerbotAIConfig.PremadeSpecName[cls][spec];
            if (configured.empty() || Lower(configured) != Lower(name))
                continue;
            int tab = BuildForTemplate(bot, sPlayerbotAIConfig.ParsedSpecLinkOrder[cls][spec][80]);
            if (ApplyBuild(bot, tab, configured, response))
                sRandomPlayerbotMgr.SetValue(bot->GetGUID().GetCounter(), "specNo", uint32(spec + 1));
            break;
        }
    }
    else if (lower.compare(0, 6, "apply ") == 0)
    {
        std::string link = Trim(command.substr(6));
        if (!EraBotBuildSelection::ValidLink(link))
            response = "Invalid talent link. Use the encoded digits-and-dashes talent link.";
        else
        {
            auto parsed = PlayerbotAIConfig::ParseTempTalentsOrder(cls, link);
            ApplyBuild(bot, BuildForTemplate(bot, parsed), "specialization selected by the link", response);
        }
    }
    else if (lower == "autopick")
    {
        int tab = int(AiFactory::GetPlayerSpecTab(bot));
        if (cls == CLASS_DRUID && tab == 1 && !EraTalentBots_ResolveSpellId(bot, 16931))
            tab = 3;
        ApplyBuild(bot, tab, "current specialization", response);
    }
    else if (lower.compare(0, 6, "switch") == 0)
        response = "Era talents have one build per era. Use talents spec <specName> to change it.";
    else
        response = "Unknown talent command. " + Help();
    return true;
}
#endif
