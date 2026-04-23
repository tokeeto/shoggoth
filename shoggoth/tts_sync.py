import json, socket, time
import re

TTS_HOST = "127.0.0.1"
TTS_PORT = 39999


def push_to_tts(saved_object: dict) -> bool:
    """Push updated cards to TTS after export. Returns False if TTS isn't running."""
    timestamp = int(time.time())

    # Cache-bust all image URLs so TTS re-fetches updated files
    bag_json_str = json.dumps(saved_object)
    # Append ?v=timestamp to all file:// URLs (replacing any existing ?v=...)
    bag_json_str = re.sub(
        r'(file:///[^"]+?)(\?v=\d+)?(")',
        rf'\1?v={timestamp}\3',
        bag_json_str
    )

    # Build a card ID -> URLs lookup for in-place table updates
    bag_data = json.loads(bag_json_str)
    cards_lookup = {}
    _extract_cards(bag_data.get("ObjectStates", []), cards_lookup)

    # Build the Lua script
    lua_script = _build_lua(cards_lookup, bag_json_str)

    # Send to TTS
    return _send_lua(lua_script)


def _extract_cards(objects: list, lookup: dict):
    """Recursively extract card id -> deck info from the bag structure."""
    for obj in objects:
        if obj.get("Name") == "Card" and obj.get("GMNotes"):
            try:
                gm = json.loads(obj["GMNotes"])
                card_id = gm.get("id")
                if card_id:
                    # Get the CustomDeck entry (there's exactly one per card)
                    deck_key = list(obj["CustomDeck"].keys())[0]
                    deck = obj["CustomDeck"][deck_key]
                    lookup[card_id] = {
                        "face": deck["FaceURL"],
                        "back": deck["BackURL"],
                        "nickname": obj.get("Nickname", ""),
                        "description": obj.get("Description", ""),
                        "gmnotes": obj.get("GMNotes", ""),
                    }
            except (json.JSONDecodeError, KeyError):
                pass
        # Recurse into bags
        if "ContainedObjects" in obj:
            _extract_cards(obj["ContainedObjects"], lookup)


def _build_cards_lua_table(cards_lookup: dict) -> str:
    """Build a native Lua table literal from the cards lookup."""
    lines = ["{"]
    for card_id, info in cards_lookup.items():
        # Escape backslashes and quotes in string values
        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  ["{esc(card_id)}"] = {{')
        lines.append(f'    face = "{esc(info["face"])}",')
        lines.append(f'    back = "{esc(info["back"])}",')
        lines.append(f'    nickname = "{esc(info["nickname"])}",')
        lines.append(f'    description = "{esc(info["description"])}",')
        lines.append(f'    gmnotes = "{esc(info["gmnotes"])}",')
        lines.append("  },")
    lines.append("}")
    return "\n".join(lines)


def _build_lua(cards_lookup: dict, bag_json_str: str) -> str:
    """Build the Lua script that TTS will execute."""
    # Encode card lookup as JSON for Lua to parse
    cards_table = _build_cards_lua_table(cards_lookup)

    # Use Lua long-string delimiters to avoid escaping issues
    # Choose a delimiter level that won't collide with content
    lua = f"""
local cardUpdates = {cards_table}
local bagJSON = [===[{bag_json_str}]===]

function shoggothUpdate()
    local updatedCount = 0

    for _, obj in ipairs(getObjects()) do
        if obj.getName() == "Shoggoth bag" then
            obj.destruct()
        elseif obj.type == "Card" then
            local ok, gmData = pcall(function()
                return JSON.decode(obj.getGMNotes())
            end)
            if ok and gmData and gmData.id and cardUpdates[gmData.id] then
                local update = cardUpdates[gmData.id]
                local customObj = obj.getCustomObject()
                customObj.face = update.face
                customObj.back = update.back
                obj.setCustomObject(customObj)
                obj.setName(update.nickname)
                obj.setDescription(update.description)
                obj.setGMNotes(update.gmnotes)
                obj.reload()
                updatedCount = updatedCount + 1
            end
        end
    end

    spawnObjectJSON({{bagJSON}})
    broadcastToAll("Shoggoth: Updated " .. updatedCount .. " cards, bag refreshed.", "Green")
end

shoggothUpdate()
"""
    return lua


def _send_lua(lua_code: str) -> bool:
    """Send Lua to TTS Global context. Returns False if TTS isn't reachable."""
    payload = json.dumps({"messageID": 3, "guid": "-1", "script": lua_code})
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((TTS_HOST, TTS_PORT))
            s.sendall(payload.encode("utf-8"))
        return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False