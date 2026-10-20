-- Headless routing regressions. Run from the repository root with Lua 5.1.
local function Setup(loaded)
  EraTalents = { state = { isEraChar = true, era = 0 }, _classId = 8 }
  dofile("client-addon/EraTalents/data/generated/Locales.lua")
  dofile("client-addon/EraTalents/data/generated/enUS/Common.lua")
  local ET = EraTalents
  local calls = { stockToggle = 0, stockOpen = 0, glyphToggle = 0, glyphOpen = 0,
                  eraToggle = 0, eraShow = 0, errors = 0, hints = 0, tab = 0, pet = 0 }
  local function Frame()
    local f = { shown = false, hooks = {}, scripts = {}, alpha = 1, mouse = true }
    function f:IsShown() return self.shown end
    function f:HookScript(name, fn)
      self.hooks[name] = self.hooks[name] or {}
      table.insert(self.hooks[name], fn)
    end
    function f:RegisterEvent() end
    function f:SetScript(name, fn) self.scripts[name] = fn end
    function f:SetAlpha(alpha) self.alpha = alpha end
    function f:EnableMouse(enabled) self.mouse = enabled end
    return f
  end
  function CreateFrame() calls.listener = Frame(); return calls.listener end
  function ShowUIPanel(f)
    if f.shown then return end
    f.shown = true
    for _, fn in ipairs(f.hooks.OnShow or {}) do fn(f) end
  end
  function HideUIPanel(f)
    if not f.shown then return end
    f.shown = false
    for _, fn in ipairs(f.hooks.OnHide or {}) do fn(f) end
  end
  PlayerTalentFrame = Frame()
  GLYPH_TALENT_TAB = 4
  PlayerSpecTab1, PlayerSpecTab2 = Frame(), Frame()
  PlayerSpecTab1.specIndex, PlayerSpecTab2.specIndex = "spec1", "petspec1"
  PlayerSpecTab1.shown, PlayerSpecTab2.shown = true, true
  for i = 3, 6 do _G["PlayerSpecTab" .. i] = nil end
  function PlayerSpecTab2:Click()
    calls.pet = calls.pet + 1
    PlayerTalentFrame.pet = true
    PlayerTalentFrame.selectedTab = 1
  end
  function PanelTemplates_GetSelectedTab(f) return f.selectedTab end
  function PlayerTalentFrame_Refresh() calls.refreshed = true end
  function PlayerTalentFrame_Toggle(pet, group)
    calls.stockToggle = calls.stockToggle + 1
    calls.lastPet, calls.lastGroup = pet, group
    if PlayerTalentFrame:IsShown() then HideUIPanel(PlayerTalentFrame)
    else ShowUIPanel(PlayerTalentFrame) end
    return "stock toggle"
  end
  function PlayerTalentFrame_Open(pet, group)
    calls.stockOpen = calls.stockOpen + 1
    calls.lastPet, calls.lastGroup = pet, group
    ShowUIPanel(PlayerTalentFrame)
    return "stock open"
  end
  local function GlyphOpen()
    if calls.throwGlyph then error("glyph failure") end
    PlayerTalentFrame.pet = false
    PlayerTalentFrame.selectedTab = GLYPH_TALENT_TAB
    ShowUIPanel(PlayerTalentFrame)
    return "glyph", nil, 42
  end
  function PlayerTalentFrame_ToggleGlyphFrame(group)
    calls.glyphToggle = calls.glyphToggle + 1
    calls.lastGroup = group
    if PlayerTalentFrame:IsShown() and PlayerTalentFrame.selectedTab == GLYPH_TALENT_TAB
        and not PlayerTalentFrame.pet then HideUIPanel(PlayerTalentFrame); return end
    return GlyphOpen()
  end
  function PlayerTalentFrame_OpenGlyphFrame(group)
    calls.glyphOpen = calls.glyphOpen + 1
    calls.lastGroup = group
    return GlyphOpen()
  end
  function PlayerTalentFrameTab_OnClick(tab)
    calls.tab = calls.tab + 1
    PlayerTalentFrame.selectedTab = tab:GetID()
    PlayerTalentFrame_Refresh()
  end
  function IsAddOnLoaded() return loaded end
  function LoadAddOn()
    loaded = true
    calls.listener.scripts.OnEvent(calls.listener, "ADDON_LOADED", "Blizzard_TalentUI")
  end
  function UnitExists() return calls.hasPet ~= false end
  UIErrorsFrame = { AddMessage = function(_, msg) calls.errors = calls.errors + 1; calls.message = msg end }
  DEFAULT_CHAT_FRAME = { AddMessage = function() calls.hints = calls.hints + 1 end }
  ET.TogglePanel = function() calls.eraToggle = calls.eraToggle + 1 end
  ET.ShowPanel = function() calls.eraShow = calls.eraShow + 1 end
  dofile("client-addon/EraTalents/Hook.lua")
  ET.InitHook()
  return ET, calls
end

local ET, calls = Setup(true)
PlayerTalentFrame_Toggle(false, 2)
assert(calls.eraToggle == 1 and calls.stockToggle == 0 and not PlayerTalentFrame:IsShown())
PlayerTalentFrame_Open(false, 2)
PlayerTalentFrame_Open(false, 2)
assert(calls.eraShow == 2 and calls.eraToggle == 1 and calls.stockOpen == 0,
  "explicit opens show instead of toggling")
ShowUIPanel(PlayerTalentFrame)
assert(not PlayerTalentFrame:IsShown() and calls.eraShow == 3, "direct Show uses the fallback")

PlayerTalentFrame_Toggle(true, 1)
assert(PlayerTalentFrame:IsShown() and PlayerTalentFrame.pet and calls.pet == 1)
assert(ET._petOnlyMode and PlayerSpecTab1.alpha == 0 and not PlayerSpecTab1.mouse)
PlayerTalentFrame_Toggle(true, 1)
assert(not PlayerTalentFrame:IsShown() and not ET._petOnlyMode)
assert(PlayerSpecTab1.alpha == 1 and PlayerSpecTab1.mouse, "pet close restores player tabs")
PlayerTalentFrame_Open(true, 1)
PlayerTalentFrame_Open(true, 1)
assert(PlayerTalentFrame:IsShown() and calls.pet == 3, "explicit pet open stays open")
HideUIPanel(PlayerTalentFrame)
calls.hasPet = false
PlayerTalentFrame_Toggle(true, 1)
assert(calls.hints == 1 and not PlayerTalentFrame:IsShown(), "missing pet shows a hint")
calls.hasPet = true

PlayerTalentFrame_ToggleGlyphFrame(1)
ET.state.era = 1
PlayerTalentFrame_OpenGlyphFrame(2)
assert(calls.errors == 2 and calls.glyphToggle == 0 and calls.glyphOpen == 0)
assert(calls.message == "Glyphs are available in the Wrath of the Lich King era.",
  "restriction explains glyph availability")
ET._classId = 6 -- Preserve the existing Death Knight exemption in either era.
local a, b, c = PlayerTalentFrame_OpenGlyphFrame(2)
assert(a == "glyph" and b == nil and c == 42, "wrapper preserves return values")
assert(PlayerTalentFrame:IsShown() and calls.lastGroup == 2 and not ET._allowStock,
  "DK glyphs bypass the fallback and restore the bypass flag")
PlayerTalentFrame_ToggleGlyphFrame(2)
assert(not PlayerTalentFrame:IsShown(), "allowed glyph toggle closes")
PlayerTalentFrame_Open(true, 1)
PlayerTalentFrame_OpenGlyphFrame(1)
assert(PlayerTalentFrame:IsShown() and not ET._petOnlyMode and PlayerSpecTab1.mouse,
  "glyphs can open from the pet-only view")
PlayerTalentFrameTab_OnClick({ GetID = function() return 1 end })
assert(not PlayerTalentFrame:IsShown() and calls.tab == 1, "player talent clicks return to era UI")
PlayerTalentFrame_Open(true, 1)
PlayerTalentFrameTab_OnClick({ GetID = function() return 1 end })
assert(PlayerTalentFrame:IsShown() and calls.tab == 2, "pet talent clicks remain stock")
-- A spec switch can leave the pet's talent tab selected on the player's spec.
PlayerTalentFrame.pet = false
PlayerTalentFrame_Refresh()
assert(not PlayerTalentFrame:IsShown(), "spec switches cannot expose the player's stock tree")
HideUIPanel(PlayerTalentFrame)

calls.throwGlyph = true
local ok, err = pcall(PlayerTalentFrame_OpenGlyphFrame, 1)
assert(not ok and string.find(err, "glyph failure", 1, true) and not ET._allowStock,
  "stock errors cannot leave the bypass enabled")
ET._allowStock = true
pcall(PlayerTalentFrame_OpenGlyphFrame, 1)
assert(ET._allowStock == true, "nested bypass state is restored")
ET._allowStock, calls.throwGlyph = nil, false

PlayerTalentFrame_OpenGlyphFrame(1)
ET._classId = 8
ET.RefreshHookState()
assert(not PlayerTalentFrame:IsShown(), "era restriction closes existing glyph view")
ET._classId = 6
PlayerTalentFrame_OpenGlyphFrame(1)
ET.RefreshHookState()
assert(PlayerTalentFrame:IsShown(), "SYNC preserves an exempt glyph view")
HideUIPanel(PlayerTalentFrame)
ET.state.era = nil
local shown = calls.eraShow
PlayerTalentFrame_OpenGlyphFrame(1)
assert(not PlayerTalentFrame:IsShown() and calls.eraShow == shown + 1,
  "unknown era retains the fallback")

ET, calls = Setup(true)
ET.state.isEraChar, ET.state.era = false, 2
assert(PlayerTalentFrame_Toggle(false, 2) == "stock toggle" and calls.lastGroup == 2)
assert(PlayerTalentFrame_Open(false, 1) == "stock open" and calls.lastGroup == 1)
ET.OpenStockTalents()
assert(not ET._petOnlyMode and PlayerSpecTab1.mouse, "Wrath retains player spec tabs")
HideUIPanel(PlayerTalentFrame)
PlayerTalentFrame_OpenGlyphFrame(1)
assert(PlayerTalentFrame:IsShown() and calls.eraShow == 0, "Wrath glyphs remain stock")
HideUIPanel(PlayerTalentFrame)
ET.state.era, ET._classId = 0, 6
PlayerTalentFrame_OpenGlyphFrame(1)
assert(PlayerTalentFrame:IsShown() and calls.eraShow == 0, "DK exemption remains stock")

ET, calls = Setup(false)
LoadAddOn("Blizzard_TalentUI")
local toggle, glyph = PlayerTalentFrame_Toggle, PlayerTalentFrame_OpenGlyphFrame
calls.listener.scripts.OnEvent(calls.listener, "ADDON_LOADED", "Blizzard_TalentUI")
ET.InitHook()
assert(toggle == PlayerTalentFrame_Toggle and glyph == PlayerTalentFrame_OpenGlyphFrame,
  "load-on-demand installation is idempotent")
PlayerTalentFrame_Toggle(false, 1)
assert(calls.eraToggle == 1 and calls.stockToggle == 0)
print("test_hook OK")
