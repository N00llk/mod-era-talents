-- Record rendering calls while exercising the real TalentUI.lua without a client.
local methods = getmetatable(UIParent).__index
function methods:ClearAllPoints() end
function methods:SetVertexColor(...) self.color = {...} end
function methods:SetTextColor(...) self.color = {...} end
function methods:SetDesaturated(value) self.desaturated = value end
function methods:GetNormalTexture() return self.normal end
local create = CreateFrame
function CreateFrame(kind, name, parent, template)
  local button = create(kind, name)
  if template == "TalentButtonTemplate" then
    for _, suffix in ipairs({"Slot", "IconTexture", "RankBorder", "Rank", "NormalTexture"}) do
      _G[name .. suffix] = create("Texture", name .. suffix)
    end
    button.normal = _G[name .. "NormalTexture"]
  end
  return button
end
function PanelTemplates_TabResize() end
function PanelTemplates_SetTab() end
GameTooltip = { lines = {} }
function GameTooltip:GetOwner() return self.owner end
function GameTooltip:SetOwner(owner) self.owner = owner end
function GameTooltip:ClearLines() self.lines = {} end
function GameTooltip:SetText(text) self.lines = {{text}} end
function GameTooltip:AddLine(...) self.lines[#self.lines + 1] = {...} end
function GameTooltip:SetHyperlink(link) self.lines = {{link}} end
function GameTooltip:Show() end
function GameTooltip:Hide() self.owner = nil end
function methods:IsMouseOver() return true end

function TestTalentView(readOnly)
  local nodes = {
    { id=1, tab=1, tier=0, col=0, name="Foundation", maxRank=5, prereqPoints=0, tooltip={"Effect"} },
    { id=2, tab=1, tier=1, col=0, name="Dependent", maxRank=2, prereqPoints=5,
      prereqTalent=1, tooltip={"Effect", "Stronger effect"} },
    { id=3, tab=1, tier=1, col=1, name="Clone", maxRank=1, prereqPoints=5,
      prereqTalent=1, tooltip={"Effect"}, grant={920000} },
  }
  local tree = { tabs={{name="Test tree"},{name="Other"},{name="Third"}}, talents=nodes }
  EraTalentsData = { [0] = { [8] = tree } }
  local view = EraTalents.NewTreeView({name="Research", defaultTab=1, readOnly=readOnly})
  local state = {era=0, availPts=1, ranks={}}
  EraTalents.RenderView(view, state, 8)
  return view, state, view.frame.pools[tree]
end
