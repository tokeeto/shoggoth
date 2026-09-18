import json, socket, time
import re

TTS_HOST = "127.0.0.1"
TTS_PORT = 39999


def rewrite_urls(wrapper: dict, path_to_url: dict) -> int:
    """Rewrite FaceURL/BackURL entries that point at a local file:/// path in
    `path_to_url` to the corresponding cloud URL, in place. `path_to_url`
    keys are local filesystem paths (as passed to publish_client.upload_file,
    i.e. os.-native separators); Windows paths are normalized to forward
    slashes before matching, since that's how they appear inside a
    file:///... URL. Returns how many URLs were changed."""
    normalized = {str(p).replace('\\', '/'): url for p, url in path_to_url.items()}
    changed = 0

    def _rewrite(url: str) -> str:
        nonlocal changed
        if not url.startswith('file:///'):
            return url
        local = url[len('file:///'):].replace('\\', '/')
        new_url = normalized.get(local)
        if new_url is None:
            return url
        changed += 1
        return new_url

    def _walk(objects: list):
        for obj in objects:
            deck = obj.get("CustomDeck")
            if isinstance(deck, dict):
                for entry in deck.values():
                    if "FaceURL" in entry:
                        entry["FaceURL"] = _rewrite(entry["FaceURL"])
                    if "BackURL" in entry:
                        entry["BackURL"] = _rewrite(entry["BackURL"])
            if "ContainedObjects" in obj:
                _walk(obj["ContainedObjects"])

    _walk(wrapper.get("ObjectStates", []))
    return changed


def push_to_tts(saved_object: dict) -> bool:
    """Push updated cards to TTS after export. Returns False if TTS isn't running."""
    timestamp = int(time.time())

    # Cache-bust all image URLs so TTS re-fetches updated files
    bag_json_str = json.dumps(saved_object)
    # Append a v=timestamp marker to every file:// and http(s):// URL
    # (replacing any existing one), so TTS re-fetches instead of using a
    # cached texture. The https branch matters once publish rewrites
    # FaceURL/BackURL to cloud URLs, which still need cache-busting on
    # re-push (PUT overwrites the same URL, it doesn't get a fresh one) --
    # unlike a bare file:/// path, a cloud URL already has its own query
    # string (?path=...), so the marker needs '&' there instead of '?'.

    def _cache_bust(match):
        url, quote = match.group(1), match.group(2)
        sep = '&' if '?' in url else '?'
        return f'{url}{sep}v={timestamp}{quote}'

    bag_json_str = re.sub(
        r'((?:file:///|https?://)[^"]+?)(?:[?&]v=\d+)?(")',
        _cache_bust,
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
                    deck_key = next(iter(obj["CustomDeck"].keys()))
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

    def escape(string):
        # Escape backslashes and quotes in string values
        if not string:
            return ''
        return string.replace("\\", "\\\\").replace('"', '\\"')

    lines = ["{"]
    for card_id, info in cards_lookup.items():
        lines.append(f'  ["{escape(card_id)}"] = {{')
        lines.append(f'    face = "{escape(info["face"])}",')
        lines.append(f'    back = "{escape(info["back"])}",')
        lines.append(f'    nickname = "{escape(info["nickname"])}",')
        lines.append(f'    description = "{escape(info["description"])}",')
        lines.append(f'    gmnotes = "{escape(info["gmnotes"])}",')
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
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False
