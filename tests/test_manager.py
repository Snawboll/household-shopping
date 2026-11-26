import sys, types, importlib.util, datetime as d
# --- minimal HA stubs ---
def mod(name):
    m = types.ModuleType(name); sys.modules[name] = m; return m
for n in ["homeassistant","homeassistant.core","homeassistant.helpers","homeassistant.helpers.storage","homeassistant.util"]:
    mod(n)
core = sys.modules["homeassistant.core"]; core.callback = lambda f: f; core.HomeAssistant = object
class Store:
    def __init__(s,*a): pass
    def async_delay_save(s,f,delay): s.saved=f()
sys.modules["homeassistant.helpers.storage"].Store = Store
dtm = mod("homeassistant.util.dt")
dtm.utcnow = lambda: d.datetime.now(d.timezone.utc)
dtm.parse_datetime = d.datetime.fromisoformat
dtm.as_local = lambda x: x
sys.modules["homeassistant.util"].dt = dtm
pkg = types.ModuleType("hs"); import os; pkg.__path__ = [os.path.join(os.path.dirname(__file__), "..", "custom_components", "household_shopping")]; sys.modules["hs"]=pkg
import importlib
const = importlib.import_module("hs.const")
manager = importlib.import_module("hs.manager")
class Bus:
    events=[]
    def async_fire(s,e,data): s.events.append((e,data))
class H: bus = Bus()
m = manager.ShoppingManager(H(), "x", "Shopping")
# staples
m.add_staple("Milk"); m.add_staple("Bread"); m.add_staple("milk")
assert len(m.staples)==2
added = m.add_staples(); assert added==["Milk","Bread"], added
assert m.add_staples()==[]
# tick staple adds only if not open
m.update_staple(m.staples[0]["uid"], None, "completed"); assert len(m.items)==2
eggs = m.add_item("Eggs", "free range")
assert m.display_description(eggs)=="free range"
# start shop, tick, unavailable via description keyword
m.start_trip("Coles")
m.update_item(m.items[0]["uid"], None, "completed", None)
m.update_item(eggs["uid"], None, None, "NA")
assert eggs["unavailable"]["store"]=="Coles", eggs
desc = m.display_description(eggs); print("desc:", desc)
assert desc.startswith("Unavailable at Coles") and desc.endswith("free range")
# unchanged description round-trip keeps flag
m.update_item(eggs["uid"], None, "needs_action", desc); assert eggs["unavailable"]
# edit only note keeps flag
lab = m.unavailable_label(eggs)
m.update_item(eggs["uid"], None, None, lab+" — any brand"); assert eggs["unavailable"] and eggs["note"]=="any brand"
assert m.bought_this_trip()==["Milk"]
rec = m.finish_trip()
print(rec)
assert rec["bought"]==["Milk"] and rec["unavailable"]==["Eggs"] and rec["remaining"]==["Bread"] and rec["store"]=="Coles"
assert [i["summary"] for i in m.items]==["Bread","Eggs"] and m.active_trip is None
# auto-start trip on tick, mark_unavailable by name, new item
m.update_item(m.items[0]["uid"], None, "completed", None); assert m.active_trip
m.mark_unavailable("oat milk", "Woolies"); assert m.find_item("Oat Milk")["unavailable"]
assert m.clear_unavailable()==2
# move
m.move_item("items", m.items[-1]["uid"], None); assert m.items[0]["summary"]=="oat milk"
print("events:", [e for e,_ in H.bus.events])
print("ALL PASS")
