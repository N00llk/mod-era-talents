#include "era_bot_commands_stubs.h"
#include "EraBotBuildSelection.h"
#include <cassert>
#include <iostream>

int main()
{
    using namespace EraBotBuildSelection;
    assert(PrimaryTab({{0, 0, 0, 5}, {1, 0, 0, 1}, {1, 0, 1, 1}}) == 0);
    assert(PrimaryTab({{2, 0, 0, 5}, {0, 0, 0, 1}}) == 2);
    assert(PrimaryTab({{0, 0, 0, 5}, {1, 0, 0, 5}}) == -1);
    assert(PrimaryTab({}) == -1);
    assert(PrimaryTab({{0}}) == -1);
    assert(PrimaryTab({{3, 0, 0, 5}}) == -1);
    assert(PrimaryTab({{0, 0, 0, 6}}) == -1);
    assert(ValidLink("005-510-1"));
    assert(!ValidLink(""));
    assert(!ValidLink("000-0"));
    assert(!ValidLink("help"));
    assert(!ValidLink("6-1"));
    assert(!ValidLink("1-2-3-4"));
    assert(!ValidLink(std::string(41, '1')));
    assert(!ValidLink(std::string(15, '5')));

    Player bot;
    std::string reply;
    auto command = [&](std::string const& text) { return EraTalentBots_HandleTalentCommand(&bot, text, reply); };
    sPlayerbotAIConfig.PremadeSpecName[8][1] = "fire pve";
    sPlayerbotAIConfig.ParsedSpecLinkOrder[8][1][80] = {{1, 0, 0, 5}, {0, 0, 0, 1}};
    assert(command("spec fire pve"));
    assert(builds == 1 && selectedTab == 1 && selectedEra == ERA_VANILLA);
    assert(trainerWalks == 1 && postWalks == 1 && ai.resets == 1 && savedSpec == 2);
    assert(reply.find("Applied Vanilla fire pve") != std::string::npos);
    bot.level = 70;
    assert(command("  spec FIRE PVE  "));
    assert(builds == 2 && selectedEra == ERA_TBC && bot.spent == 61);
    assert(reply.find("Applied TBC fire pve") != std::string::npos);
    assert(command("spec list"));
    assert(reply.find("fire pve -> tree 2") != std::string::npos);
    assert(command("spec missing") && builds == 2);
    assert(command("apply bad link") && builds == 2);
    assert(command("switch 2") && builds == 2);
    assert(command("autopick") && selectedTab == 2 && builds == 3);
    bot.combat = true;
    assert(command("spec fire pve") && builds == 3);
    bot.combat = false;
    haveSpell = false;
    assert(command("spec fire pve") && builds == 3 && bot.spent == 61);
    haveSpell = true;
    node.rankSpell.clear();
    assert(command("spec fire pve") && builds == 3);
    node.rankSpell = {123};
    config.enabled = false;
    assert(!command("spec fire pve") && builds == 3);
    config.enabled = true;
    bot.level = 80;
    assert(!command("spec fire pve") && builds == 3);
    bot.level = 60;
    bot.bot = false;
    assert(!command("spec fire pve") && builds == 3);
    bot.bot = true;
    haveNodes = false;
    assert(!command("spec fire pve") && builds == 3);
    haveNodes = true;
    bot.cls = 11;
    linkTemplate = {{1, 1, 0, 3}, {1, 0, 0, 5}};
    assert(command("apply 530") && selectedTab == 1 && builds == 4);
    linkTemplate = {{1, 0, 0, 5}};
    assert(command("apply 500") && selectedTab == 3 && builds == 5);
    linkTemplate = {{0, 0, 0, 5}, {1, 0, 0, 5}};
    assert(command("apply 5-5") && builds == 5);
    bot.level = 9;
    linkTemplate = {{1, 0, 0, 5}};
    assert(command("apply 500") && builds == 5);
    assert(reply.find("level 10") != std::string::npos);
    std::cout << "Era bot command routing, build selection, and rejection checks passed\n";
}
