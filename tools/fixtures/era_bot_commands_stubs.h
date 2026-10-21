// Dependencies for testing the real command dispatcher without compiling the server.
#pragma once
#define MOD_ERA_TALENT_BOTS_H
#define MOD_ERA_TALENT_CONTENT_H
#define MOD_ERA_TALENTS_H
#define MOD_ERA_TALENTS_CONFIG_H
#include <array>
#include <cstdint>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
enum EraId : uint8 { ERA_VANILLA, ERA_TBC, ERA_WOTLK };
constexpr uint32 CLASS_DRUID = 11, CLASS_SHAMAN = 7, SKILL_DUAL_WIELD = 118;
constexpr int MAX_SPECNO = 20;
struct Guid { uint32 GetCounter() const { return 1; } };
struct Player
{
    uint8 cls = 8, level = 60;
    bool bot = true, alive = true, combat = false, world = true;
    int spent = 51;
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    bool IsAlive() const { return alive; }
    bool IsInCombat() const { return combat; }
    bool IsInWorld() const { return world; }
    Guid GetGUID() const { return {}; }
    void SetSkill(uint32, uint32, uint32, uint32) {}
    void SetCanDualWield(bool) {}
};
struct PlayerbotAI { int resets = 0; void ResetStrategies() { ++resets; } };
inline PlayerbotAI ai;
inline PlayerbotAI* GET_PLAYERBOT_AI(Player*) { return &ai; }
struct Config
{
    bool enabled = true;
    bool BotTalents() const { return enabled; }
};
inline Config config;
inline Config* sEraTalentsConfig = &config;
struct EraTalentNode { uint8 maxRank = 1; std::vector<uint32> rankSpell = {123}; };
inline EraTalentNode node;
inline bool haveNodes = true, haveSpell = true;
struct Content
{
    std::vector<EraTalentNode const*> NodesFor(uint8, uint8) { return haveNodes ? std::vector<EraTalentNode const*>{&node} : std::vector<EraTalentNode const*>{}; }
};
inline Content content;
inline Content* sEraTalentContent = &content;
struct SpellMgr { void const* GetSpellInfo(uint32) { return haveSpell ? this : nullptr; } };
inline SpellMgr spellMgr;
inline SpellMgr* sSpellMgr = &spellMgr;
struct TalentEntry { uint32 Row = 1, Col = 0; uint32 RankID[5] = {16931}; };
struct TalentStore
{
    uint32 GetNumRows() { return 1; }
    TalentEntry const* LookupEntry(uint32) { static TalentEntry talent; return &talent; }
};
inline TalentStore sTalentStore;
struct PlayerbotAIConfig
{
    std::string PremadeSpecName[12][MAX_SPECNO];
    std::vector<std::vector<uint32>> ParsedSpecLinkOrder[12][MAX_SPECNO][81];
    static std::vector<std::vector<uint32>> ParseTempTalentsOrder(uint32, std::string);
};
inline PlayerbotAIConfig sPlayerbotAIConfig;
inline std::vector<std::vector<uint32>> linkTemplate;
inline std::vector<std::vector<uint32>> PlayerbotAIConfig::ParseTempTalentsOrder(uint32, std::string) { return linkTemplate; }
inline int builds = 0, selectedTab = -1, trainerWalks = 0, postWalks = 0, savedSpec = 0;
inline EraId selectedEra = ERA_WOTLK;
struct PlayerbotFactory
{
    PlayerbotFactory(Player*, uint8) {}
    void InitAvailableSpells() { ++trainerWalks; }
};
struct RandomMgr { void SetValue(uint32, char const*, uint32 value) { savedSpec = int(value); } };
inline RandomMgr sRandomPlayerbotMgr;
namespace AiFactory { inline uint32 GetPlayerSpecTab(Player*) { return 2; } }
namespace EraTalentBots
{
    inline void InvalidateSpecCache(Player*) {}
    inline bool IsBot(Player* p) { return p && p->bot; }
    inline EraId BotEra(Player* p) { return p->level <= 60 ? ERA_VANILLA : p->level <= 70 ? ERA_TBC : ERA_WOTLK; }
    inline bool IsEraManaged(Player* p) { return BotEra(p) != ERA_WOTLK; }
    inline bool FactoryReconcile(Player* p, int tab)
    {
        ++builds;
        selectedTab = tab;
        selectedEra = BotEra(p);
        p->spent = p->level - 9;
        return true;
    }
}
namespace EraTalents
{
    inline int SpentPoints(Player* p, EraId) { return p->spent; }
    inline int AvailablePoints(Player* p, EraId) { return p->level - 9 - p->spent; }
}
inline bool EraTalentBots_SpecTabs(Player*, uint32* tabs) { tabs[2] = 51; return true; }
inline uint32 EraTalentBots_ResolveSpellId(Player*, uint32) { return 0; }
inline void EraTalentBots_PostTrainerWalk(Player*) { ++postWalks; }
bool EraTalentBots_HandleTalentCommand(Player*, std::string const&, std::string&);
