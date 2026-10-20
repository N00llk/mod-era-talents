-- Replace the stock talent frame for era characters. WotLK chars keep Blizzard's.
-- Path-independent: guard PlayerTalentFrame:OnShow so EVERY opener (micro-button, the
-- N keybind, a macro) is intercepted. Hooking ToggleTalentFrame alone missed the
-- micro-button on 3.3.5a (only the keybind routed through it).
EraTalents = EraTalents or {}
local ET = EraTalents

local function IsEraCharacter()
  return ET.state and ET.state.isEraChar
end

local function GlyphsBlockedByEra()
  return ET.state and ET.state.era and ET.state.era < 2 and ET._classId ~= 6
end

-- Stock openers and their OnShow scripts run synchronously. Always restore the bypass,
-- including when a stock function (or another addon's hook) raises an error.
local function WithStockAllowed(fn, ...)
  local previous = ET._allowStock
  ET._allowStock = true
  local function Pack(...) return { n = select("#", ...), ... } end
  local results = Pack(pcall(fn, ...))
  ET._allowStock = previous
  if not results[1] then error(results[2], 0) end
  return unpack(results, 2, results.n)
end

local function GuardStockTalentRoutes()
  if ET._stockTalentRoutesWrapped or not PlayerTalentFrame_Toggle then return end
  ET._stockTalentRoutesWrapped = true
  local stockToggle = PlayerTalentFrame_Toggle
  PlayerTalentFrame_Toggle = function(pet, ...)
    if not ET._allowStock and IsEraCharacter() then
      if pet then
        if PlayerTalentFrame:IsShown() and ET._petOnlyMode then
          HideUIPanel(PlayerTalentFrame)
        else
          ET.OpenStockTalents()
        end
      else
        ET.TogglePanel()
      end
      return
    end
    return stockToggle(pet, ...)
  end

  local stockOpen = PlayerTalentFrame_Open
  if stockOpen then
    PlayerTalentFrame_Open = function(pet, ...)
      if not ET._allowStock and IsEraCharacter() then
        if pet then return ET.OpenStockTalents() end
        return ET.ShowPanel()
      end
      return stockOpen(pet, ...)
    end
  end

  -- Glyphs share the player's stock talent tabs. Guard refreshes too: switching from
  -- a pet spec to a player spec can select a talent tree without clicking a talent tab.
  local stockRefresh = PlayerTalentFrame_Refresh
  if stockRefresh then
    PlayerTalentFrame_Refresh = function(...)
      if not ET._allowStock and IsEraCharacter() and PlayerTalentFrame:IsShown() and not PlayerTalentFrame.pet
          and PanelTemplates_GetSelectedTab(PlayerTalentFrame) ~= GLYPH_TALENT_TAB then
        HideUIPanel(PlayerTalentFrame)
        return ET.ShowPanel()
      end
      return stockRefresh(...)
    end
  end
end

local function GlyphUnavailable()
  local msg = ET.L.GLYPHS_UNAVAILABLE
  UIErrorsFrame:AddMessage(msg, 1, 0.2, 0.2, 1, 3)
end

local function GuardStockGlyphRoutes()
  ET._stockGlyphRoutesWrapped = ET._stockGlyphRoutesWrapped or {}
  for _, name in ipairs({ "PlayerTalentFrame_ToggleGlyphFrame", "PlayerTalentFrame_OpenGlyphFrame" }) do
    local stockGlyph = _G[name]
    if stockGlyph and not ET._stockGlyphRoutesWrapped[name] then
      _G[name] = function(...)
        if GlyphsBlockedByEra() then return GlyphUnavailable() end
        if ET.state and ET.state.era ~= nil then
          -- Leaving the pet-only view restores player spec tabs before opening glyphs.
          if ET._petOnlyMode then HideUIPanel(PlayerTalentFrame) end
          return WithStockAllowed(stockGlyph, ...)
        end
        -- Era has not arrived yet: retain the stock/fallback behavior.
        return stockGlyph(...)
      end
      ET._stockGlyphRoutesWrapped[name] = true
    end
  end
end

local function GuardStockFrame()
  if not PlayerTalentFrame then return end
  GuardStockTalentRoutes()
  GuardStockGlyphRoutes()
  if PlayerTalentFrame._eraGuarded then return end
  PlayerTalentFrame._eraGuarded = true
  PlayerTalentFrame:HookScript("OnShow", function(self)
    -- Pet and era-allowed glyph openers temporarily bypass this guard. Both views
    -- live in the stock frame; only the player's talent tree is replaced by the era panel.
    if ET._allowStock then return end
    if ET.state and ET.state.isEraChar then
      HideUIPanel(self)     -- era chars never see the WotLK tree...
      ET.ShowPanel()        -- ...a direct stock-panel open shows their era tree
    end
  end)
end

-- Land the stock frame directly on the PET talent view. The pet spec tab is the PlayerSpecTab
-- whose specIndex is a "petspec..." string (diag-confirmed on this 3.3.5a build: player specs are
-- "spec1"/"spec2", the pet is "petspec1"); clicking it shows the CURRENT pet's OWN tree -- Blizzard's
-- GetPetTalentTree() resolves Ferocity / Cunning / Tenacity from the active pet, so swapping pets and
-- reopening shows the right tree with no hardcoding -- and it auto-hides the player talent-tree tabs
-- and the Glyphs tab (they only show on a player spec). No pet out => no pet spec tab; hint instead.
local function IsPetSpecTab(tab)
  return tab and type(tab.specIndex) == "string" and tab.specIndex:find("petspec") ~= nil
end

local function SelectPetSpec()
  for i = 1, 6 do
    local tab = _G["PlayerSpecTab" .. i]
    if tab and tab:IsShown() and IsPetSpecTab(tab) then
      tab:Click()
      return true
    end
  end
  return false
end

-- Confine an era hunter to the PET spec tab: while ET._petOnlyMode is set, the player (non-pet)
-- spec tabs are made invisible AND unclickable so the WotLK player talent tree is unreachable.
-- We SetAlpha(0)+EnableMouse(false) rather than Hide() -- Hide() flips IsShown(), which Blizzard's
-- own PlayerTalentFrame layout reads and would fight (and it is the more taint-prone path), whereas
-- alpha/mouse leave its bookkeeping untouched. Re-applied through each tab's OnShow (Blizzard
-- re-shows tabs on every frame update) and fully restored when the frame closes, so a WotLK-era
-- char reaching the frame normally keeps every tab interactive.
local function ApplyPetOnly(tab)
  if ET._petOnlyMode and not IsPetSpecTab(tab) then
    tab:SetAlpha(0); tab:EnableMouse(false)
  else
    tab:SetAlpha(1); tab:EnableMouse(true)
  end
end

local function GuardPlayerSpecTabs()
  for i = 1, 6 do
    local tab = _G["PlayerSpecTab" .. i]
    if tab then
      if not tab._eraPetGuarded then
        tab._eraPetGuarded = true
        tab:HookScript("OnShow", function(self) ApplyPetOnly(self) end)
      end
      ApplyPetOnly(tab)   -- apply to whatever is shown right now
    end
  end
  if PlayerTalentFrame and not PlayerTalentFrame._eraPetHideHooked then
    PlayerTalentFrame._eraPetHideHooked = true
    PlayerTalentFrame:HookScript("OnHide", function()
      ET._petOnlyMode = false
      for i = 1, 6 do
        local t = _G["PlayerSpecTab" .. i]
        if t then t:SetAlpha(1); t:EnableMouse(true) end
      end
    end)
  end
end

-- Open the STOCK WotLK talent frame on demand, bypassing the era guard exactly once, jump straight
-- to the Pet talent tab that the era window deliberately does not replace, and confine the view to
-- pet-only. Requires a pet out (the pet spec tab only exists then). Blizzard_TalentUI is
-- load-on-demand, and LoadAddOn fires ADDON_LOADED synchronously, so GuardStockFrame is attached
-- before we Show; ShowUIPanel fires OnShow synchronously too, so the spec tabs are populated.
function ET.OpenStockTalents()
  if not UnitExists("pet") then
    DEFAULT_CHAT_FRAME:AddMessage(ET.L.SUMMON_PET)
    return
  end
  if not IsAddOnLoaded("Blizzard_TalentUI") then LoadAddOn("Blizzard_TalentUI") end
  if PlayerTalentFrame then
    WithStockAllowed(function()
      ET._petOnlyMode = IsEraCharacter() and true or false
      ShowUIPanel(PlayerTalentFrame)
      if not PlayerTalentFrame:IsShown() then ET._petOnlyMode = false; return end
      GuardPlayerSpecTabs()   -- attach OnShow guards + hide player tabs now (catches the click cascade)
      SelectPetSpec()         -- land on the pet's own tree (correct per active pet)
    end)
  end
end

-- SYNC may change eras while a stock window is already visible.
function ET.RefreshHookState()
  if not PlayerTalentFrame or not PlayerTalentFrame:IsShown() or ET._allowStock then return end
  if not IsEraCharacter() then
    if ET._petOnlyMode then
      ET._petOnlyMode = false
      GuardPlayerSpecTabs()
    end
    return
  end
  if ET._petOnlyMode and PlayerTalentFrame.pet then return end
  if ET.state.era ~= nil and not GlyphsBlockedByEra() and not PlayerTalentFrame.pet
      and PanelTemplates_GetSelectedTab(PlayerTalentFrame) == GLYPH_TALENT_TAB then return end
  HideUIPanel(PlayerTalentFrame)
  ET.ShowPanel()
end

function ET.InitHook()
  if ET._hooked then return end
  ET._hooked = true
  -- Blizzard_TalentUI is load-on-demand: guard now if already loaded, else when it loads.
  if IsAddOnLoaded("Blizzard_TalentUI") then GuardStockFrame() end
  local w = CreateFrame("Frame")
  w:RegisterEvent("ADDON_LOADED")
  w:SetScript("OnEvent", function(self, event, name)
    if name == "Blizzard_TalentUI" then GuardStockFrame() end
  end)
end
