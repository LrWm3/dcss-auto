local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local name,value=debug.getupvalue(fn,i)
    if not name then break end
    if name==wanted then return value end
    if type(value)=="function" then local r=find(value,wanted,seen); if r then return r end end
  end
end
local options=assert(find(ready,"wand_options"))
local action=assert(find(ready,"combat_wand_action"))
local turn,rage,spent,hp=100,false,false,10
you={turns=function() return turn end,berserk=function() return rage end,
  confused=function() return false end,hp=function() return hp,100 end,
  branch=function() return "D" end,depth=function() return 10 end,
  slowed=function() return false end,exhausted=function() return false end,
  turn_is_over=function() return spent end}
crawl.mpr=function() end
local function monster(attitude,injury)
  return {name=function() return "ogre" end,attitude=function() return attitude or 0 end,
    damage_level=function() return injury or 0 end,
    defeat_wl=function(self,spell) return spell=="Charm" and 62 or 81 end}
end
local scan={any=true,worst=2,monsters={},cells={}}
for x=0,4 do for y=0,1 do scan.cells[x..":"..y]={x=x,y=y,visible=true,traversable=true} end end
for _,x in ipairs({3,4}) do
  local m=monster()
  scan.cells[x..":0"].monster=m
  scan.monsters[#scan.monsters+1]={x=x,y=0,monster=m,threat=2}
end
local inventory={}
for slot,name in ipairs({"charming","mindburst","warping"}) do
  inventory[#inventory+1]={slot=slot,plus=10,is_identified=true,
    class=function() return "wand" end,name=function() return "wand of "..name end}
end
local fired=0
items={inventory=function() return inventory end,index_to_letter=function() return "f" end}
crawl.process_keys=function(keys)
  assert(keys=="Vfrlllf\027\027\027","explicit wand menu and player-relative target")
  fired=fired+1
end
local result=options(scan)
assert(result[1].kind=="charming" and result[1].x==3)
assert(result[2].kind=="warping","safe front blast considered")
rage=true; assert(#options(scan)==0); rage=false
scan.cells["2:0"].monster=monster(1)
assert(#options(scan)==0,"intervening ally blocks shots")
scan.cells["2:0"].monster=nil
scan.cells["3:1"].monster=monster(1)
assert(#options(scan)==0,"ally vetoes charm and unsafe blast")
scan.cells["3:1"].monster=nil
inventory[1].plus=0; inventory[3].plus=0
scan.monsters[1].monster.damage_level=function() return 4 end
assert(options(scan)[1].kind=="mindburst","wounded threat prioritised")
assert(not action(scan) and fired==1)
assert(not action(scan) and fired==1,"rejected shot cannot repeat same turn")
turn=101; spent=true
assert(action(scan) and fired==2)
assert(AUTOCrawl_WAND_STATE.uses==1,"only spent actions count")
local scores=assert(find(ready,"wand_scores"))
for _,pair in ipairs({{100,10},{99,9},{90,9},{89,8},{10,1},{9,0}}) do
  hp=pair[1]; assert(scores(scan)==pair[2])
end
hp=20; assert(#options(scan)==0,"equality must not allow wands")
scan.monsters[2].threat=3
local h,t=scores(scan); assert(h==2 and t==7)
hp=10
local notes={}; crawl.take_note=function(s) notes[#notes+1]=s end
for n=102,104 do turn=n; assert(action(scan)) end
assert(AUTOCrawl_WAND_STATE.uses==4 and #notes==1)
assert(notes[1]:find("ogre",1,true) and notes[1]:find("threat 3",1,true))
turn=200; assert(not action(scan),"time alone must not reset cap")
assert(#notes==1,"cap note must not spam every turn")
local save=c_save(); AUTOCrawl_WAND_STATE=nil; assert(load(save))()
assert(AUTOCrawl_WAND_STATE.uses==4,"cap survives save/load")
local observe=assert(find(ready,"observe_wand_encounter"))
local empty={any=false,monsters={}}
BOT.encounter={active=true}; hp=100; observe(empty)
assert(AUTOCrawl_WAND_STATE.active,"brief LOS loss retains budget")
BOT.encounter.active=false; observe(empty)
assert(not AUTOCrawl_WAND_STATE.active)
hp=10; turn=201; assert(#options(scan)>0 and AUTOCrawl_WAND_STATE.uses==0)
print("wand regression cases passed")
