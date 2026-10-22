-- 3.3.5 clients can receive NOT_IN_LFG without a matching stock GlobalString.
-- Install before login channel notices; preserve client/other-addon translations.
local notice = EraTalents.L.CHANNEL_NOT_IN_LFG
if type(CHAT_NOT_IN_LFG_NOTICE) ~= "string" then
  CHAT_NOT_IN_LFG_NOTICE = notice
end
if type(CHAT_NOT_IN_LFG_NOTICE_BN) ~= "string" then
  CHAT_NOT_IN_LFG_NOTICE_BN = notice
end
