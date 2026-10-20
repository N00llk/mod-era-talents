-- Minimal 3.3.5 API surface for loading a release in TOC order and firing login.
testFrames, testChat, testSent = {}, {}, {}
local methods = {}
local function Widget(name)
  return setmetatable({ name = name, scripts = {}, events = {}, shown = true }, { __index = methods })
end
function methods:GetName() return self.name end
function methods:SetText(text) self.text = text end
function methods:GetText() return self.text end
function methods:GetFrameLevel() return 1 end
function methods:IsShown() return self.shown end
function methods:Hide() self.shown = false end
function methods:Show() self.shown = true end
function methods:RegisterEvent(event) self.events[event] = true end
function methods:SetScript(event, handler) self.scripts[event] = handler end
function methods:CreateTexture() return Widget() end
function methods:CreateFontString() return Widget() end
for _, name in ipairs({ "SetFrameStrata", "SetToplevel", "SetWidth", "SetHeight", "SetPoint",
    "EnableMouse", "SetTexture", "SetTexCoord", "SetAllPoints", "SetJustifyH",
    "EnableMouseWheel", "SetScrollChild", "SetFrameLevel" }) do
  methods[name] = function() end
end
function CreateFrame(_, name)
  local frame = Widget(name)
  if name then _G[name] = frame end
  testFrames[#testFrames + 1] = frame
  return frame
end
UIParent = Widget("UIParent")
UIPanelWindows, SlashCmdList = {}, {}
function UnitClass() return "Паладин", "PALADIN" end
function UnitName() return "Tester" end
function IsAddOnLoaded() return false end
function SetPortraitTexture() end
function PanelTemplates_SetNumTabs() end
function hooksecurefunc() end
function SendAddonMessage(prefix, payload, channel, target)
  testSent[#testSent + 1] = payload
end
DEFAULT_CHAT_FRAME = { AddMessage = function(_, text) testChat[#testChat + 1] = text end }

function TestEnterWorld()
  -- Use a snapshot: login creates the communications and load-on-demand listeners.
  local frames = {}
  for index, frame in ipairs(testFrames) do frames[index] = frame end
  for _, frame in ipairs(frames) do
    if frame.events.PLAYER_ENTERING_WORLD then frame.scripts.OnEvent(frame, "PLAYER_ENTERING_WORLD") end
  end
end
