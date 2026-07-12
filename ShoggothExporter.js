useLibrary("threads");
importClass(java.io.File);
importClass(java.nio.file.Files);
importClass(java.nio.file.Paths);
importClass(arkham.project.ProjectUtilities);
importClass(ca.cgjennings.apps.arkham.project.Project);
importClass(javax.imageio.ImageIO);

const PROJECT = Eons.getOpenProject();
const PROJECT_FOLDER = new File(PROJECT.getFile().getPath(), "shoggoth_export");
if (!PROJECT_FOLDER.exists()) PROJECT_FOLDER.mkdirs();
const IMAGE_FOLDER = new File(PROJECT_FOLDER, "images");
if (!IMAGE_FOLDER.exists()) IMAGE_FOLDER.mkdirs();
const OUTPUT_FILE = new File(PROJECT_FOLDER, "project.json");

const front_types = {
    "Act.js": "act",
    "ActAssetStory.js": "act",
    "ActEnemy.js": "act",
    "ActLocation.js": "act",
    "ActPortrait.js": "act",
    "Agenda.js": "agenda",
    "AgendaAssetStory.js": "agenda",
    "AgendaEnemy.js": "agenda",
    "AgendaFrontPortrait.js": "agenda",
    "AgendaLocation.js": "agenda",
    "AgendaPortrait.js": "agenda",
    "AgendaTreachery.js": "agenda",
    "Asset.js": "asset",
    "AssetAsset.js": "asset",
    "AssetStory.js": "asset",
    "AssetStoryAsset.js": "asset",
    "AssetStoryEnemy.js": "asset",
    "AssetStoryPortrait.js": "asset",
    "Chaos.js": "chaos",
    "Concealed.js": "concealed",
    "Customizable.js": "customizable",
    "Enemy.js": "enemy",
    "EnemyEnemy.js": "enemy",
    "EnemyLocation.js": "enemy_location",
    "EnemyPortrait.js": "enemy",
    "Event.js": "event",
    "Investigator.js": "investigator",
    "InvestigatorStory.js": "investigator",
    "Key.js": "key",
    "Location.js": "location",
    "LocationLocation.js": "location",
    "Scenario.js": "scenario",
    "Skill.js": "skill",
    "StoryAsset.js": "story",
    "StoryChaos.js": "story",
    "StoryEnemy.js": "story",
    "StoryLocation.js": "story",
    "StoryStory.js": "story",
    "StoryTreachery.js": "story",
    "Treachery.js": "treachery",
    "TreacheryLocation.js": "treachery",
    "TreacheryPortrait.js": "treachery",
    "TreacheryStory.js": "treachery",
    "Ultimatum.js": "ultimatum",
    "WeaknessEnemy.js": "enemy",
    "WeaknessTreachery.js": "treachery",
    "MiniInvestigator.js": "mini_investigator",
};

const back_types = {
    "Act.js": "act_back",
    "ActAssetStory.js": "asset",
    "ActEnemy.js": "enemy",
    "ActLocation.js": "location",
    "ActPortrait.js": "act_back",
    "Agenda.js": "agenda_back",
    "AgendaAssetStory.js": "asset",
    "AgendaEnemy.js": "enemy",
    "AgendaFrontPortrait.js": "agenda_back",
    "AgendaLocation.js": "location",
    "AgendaPortrait.js": "agenda_back",
    "AgendaTreachery.js": "treachery",
    "Asset.js": "player",
    "AssetAsset.js": "asset",
    "AssetStory.js": "story",
    "AssetStoryAsset.js": "asset",
    "AssetStoryEnemy.js": "enemy",
    "AssetStoryPortrait.js": "story",
    "Chaos.js": "chaos",
    "Concealed.js": "concealed_back",
    "Customizable.js": "customizable_back",
    "Enemy.js": "encounter",
    "EnemyEnemy.js": "enemy",
    "EnemyLocation.js": "location_back",
    "EnemyPortrait.js": "encounter",
    "Event.js": "player",
    "Investigator.js": "investigator_back",
    "InvestigatorStory.js": "investigator_back",
    "Key.js": "key_back",
    "Location.js": "location_back",
    "LocationLocation.js": "location",
    "Scenario.js": "scenario_back",
    "Skill.js": "player",
    "StoryAsset.js": "asset",
    "StoryChaos.js": "chaos",
    "StoryEnemy.js": "enemy",
    "StoryLocation.js": "location",
    "StoryStory.js": "story",
    "StoryTreachery.js": "treachery",
    "Treachery.js": "encounter",
    "TreacheryLocation.js": "location",
    "TreacheryPortrait.js": "encounter",
    "TreacheryStory.js": "story",
    "Ultimatum.js": "ultimatum_back",
    "WeaknessEnemy.js": "player",
    "WeaknessTreachery.js": "player",
    "MiniInvestigator.js": "mini_investigator_back",
};

// Shoggoth defaults for these types use a coordinate space that matches
// neither the SE template nor the standard shoggoth card space, so we skip
// illustration pan/scale and let shoggoth's default region-fit apply.
const GEOMETRY_SKIP = {
    "Key.js": true,
    "EnemyLocation.js": true,
    "Scenario.js": true,
    "Ultimatum.js": true,
};

// The released plugin's card templates are 375x525 (525x375 landscape)
// content with no bleed, while shoggoth's region space is 1500x2100 content
// behind a 72px bleed — all geometry scales x4 and shifts +72. Mini templates
// are 244x375 mapping onto shoggoth's mini content of 1000x1537.
const GEOMETRY_DEFAULT_TRANSFORM = { scale: 1500 / 375, offset: 72 };
const GEOMETRY_TRANSFORM = {
    "Concealed.js": { scale: 1000 / 244, offset: 72 },
    "MiniInvestigator.js": { scale: 1000 / 244, offset: 72 },
};

// script name → shoggoth guide "format" (paper size)
const GUIDE_SCRIPTS = {
    "Guide75.js": "75x95",
    "GuideA4.js": "a4",
    "GuideLetter.js": "letter",
};

const PORTRAITS = {
    "Act.js": ["Portrait-Front", "Collection-Both", "Encounter-Both"],
    "ActAssetStory.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "ActEnemy.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "ActLocation.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "ActPortrait.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "Agenda.js": ["Portrait-Front", "Collection-Both", "Encounter-Both"],
    "AgendaAssetStory.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "AgendaEnemy.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "AgendaFrontPortrait.js": [
        "Portrait-Front",
        "Collection-Both",
        "Encounter-Both",
    ],
    "AgendaLocation.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "AgendaPortrait.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "AgendaTreachery.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "Asset.js": ["Portrait-Front", "Collection-Front"],
    "AssetAsset.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
    ],
    "AssetStory.js": ["Portrait-Front", "Collection-Front", "Encounter-Front"],
    "AssetStoryAsset.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "AssetStoryEnemy.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "AssetStoryPortrait.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "BoxCover.js": ["Portrait-Front", "PortraitBottom-Front"],
    "Chaos.js": ["Collection-Both", "Encounter-Both"],
    "Concealed.js": ["Portrait-Front"],
    "Customizable.js": ["Collection-Front"],
    "Divider.js": ["Encounter-Both"],
    "Enemy.js": ["Portrait-Front", "Collection-Front", "Encounter-Front"],
    "EnemyEnemy.js": [
        "Portrait-Both",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "EnemyLocation.js": [
        "Portrait-Both",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "EnemyPortrait.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "Event.js": ["Portrait-Front", "Collection-Front", "Encounter-Both"],
    "Guide75.js": ["Portrait1-Front", "Portrait2-Front"],
    "GuideA4.js": ["Portrait1-Front", "Portrait2-Front"],
    "GuideLetter.js": ["Portrait1-Front", "Portrait2-Front"],
    "Investigator.js": [
        "TransparentPortrait-Both",
        "Portrait-Back",
        "Collection-Front",
    ],
    "InvestigatorStory.js": [
        "TransparentPortrait-Both",
        "Portrait-Back",
        "Collection-Front",
        "Encounter-Both",
    ],
    "Key.js": [
        "Portrait-Both",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "Location.js": [
        "Portrait-Both",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "LocationLocation.js": [
        "Portrait-Both",
        "BackPortrait-Back",
        "Collection-Both",
        "Encounter-Both",
    ],
    "MiniInvestigator.js": ["Portrait-Both"],
    "PackCover.js": ["Portrait-Front"],
    "Scenario.js": [
        "Portrait",
        "BackPortrait",
        "Collection-Both",
        "Encounter-Both",
    ],
    "Skill.js": ["Portrait-Front", "Collection-Front", "Encounter-Both"],
    "StoryAsset.js": ["BackPortrait-Back", "Collection-Back", "Encounter-Both"],
    "StoryChaos.js": ["Collection-Back", "Encounter-Both"],
    "StoryEnemy.js": ["BackPortrait-Back", "Collection-Back", "Encounter-Both"],
    "StoryLocation.js": [
        "BackPortrait-Back",
        "Collection-Back",
        "Encounter-Both",
    ],
    "StoryStory.js": ["Collection-Both", "Encounter-Both"],
    "StoryTreachery.js": [
        "BackPortrait-Back",
        "Collection-Back",
        "Encounter-Both",
    ],
    "Treachery.js": ["Portrait-Front", "Collection-Front", "Encounter-Front"],
    "TreacheryLocation.js": [
        "Portrait-Front",
        "Collection-Front",
        "Encounter-Front",
    ],
    "TreacheryPortrait.js": [
        "Portrait-Front",
        "BackPortrait-Back",
        "Collection-Front",
        "Encounter-Front",
    ],
    "TreacheryStory.js": [
        "Portrait-Front",
        "Collection-Both",
        "Encounter-Both",
    ],
    "Ultimatum.js": ["Portrait", "Collection", "Encounter"],
    "WeaknessEnemy.js": [
        "Portrait-Front",
        "Collection-Front",
        "Encounter-Front",
    ],
    "WeaknessTreachery.js": [
        "Portrait-Front",
        "Collection-Front",
        "Encounter-Front",
    ],
};

// SE markup tag → shoggoth tag (see rich_text.py:font_icon_tags for valid targets)
const TAG_MAP = {
    "<fullname>": "<name>",
    "<act>": "<action>",
    "<acts>": "<action>",
    "<fre>": "<free>",
    "<rea>": "<reaction>",
    "<wil>": "<willpower>",
    "<int>": "<intellect>",
    "<agi>": "<agility>",
    "<com>": "<combat>",
    "<rog>": "<rogue>",
    "<see>": "<seeker>",
    "<sur>": "<survivor>",
    "<gua>": "<guardian>",
    "<mys>": "<mystic>",
    "<sku>": "<skull>",
    "<cul>": "<cultist>",
    "<tab>": "<tablet>",
    "<mon>": "<elder_thing>",
    "<eld>": "<elder_sign>",
    "<ten>": "<auto_fail>",
    "<ble>": "<blessing>",
    "<cur>": "<curse>",
    "<spa>": "<spawn>",
    "<gbul>": "<bullet>",
    "<bul>": "<bullet>",
    "<dmg>": "<damage>",
    "<hor>": "<horror>",
    "<rec>": "<resource>",
    "<cod>": "<codex>",
    "<fro>": "<frost>",
    "<seal1>": "<sign_1>",
    "<seal2>": "<sign_2>",
    "<seal3>": "<sign_3>",
    "<seal4>": "<sign_4>",
    "<seal5>": "<sign_5>",
    "<ast>": "<star>",
    "<uni>": "<unique>",
    // in running text shoggoth uses the large per-investigator glyph;
    // the small <per> is reserved for stat fields (health/clues/shroud/...),
    // where the exporter appends it directly without going through this map
    "<per>": "<investigator>",
    // stripped: spacers and tab-bullets have no shoggoth equivalent
    "<bultab>": "",
    "<vs>": "",
    "<svs>": "",
    "<lvs>": "",
    "<hs>": "",
    "<shs>": "",
    "<lhs>": "",
};

function translate_tags(value) {
    for (let tag in TAG_MAP) {
        value = value.split(tag).join(TAG_MAP[tag]);
    }
    return value;
}

function translate_text(value) {
    if (!value) return value;
    value = String(value);
    value = value.replace(/^\n/, "");  // remove empty first lines
    value = translate_tags(value);
    let match = value.match(/\n+$/);
    let trailing = match ? match[0] : "";
    let body = trailing ? value.slice(0, value.length - trailing.length) : value;
    body = body.replace(/\n\n/g, "\n");
    // exactly one trailing empty line is SE's spacing in front of the flavor
    // text (shoggoth adds its own gap) — drop it; two or more are deliberate
    return trailing.length === 1 ? body : body + trailing;
}

// SE renders an investigator-back label as '<hdr>' + label + '</hdr>: ' — the
// label itself may toggle out of the header style with embedded </hdr>…<hdr>
// (e.g. 'Deckbuilding Requirements</hdr> (do not count toward deck size)<hdr>').
// Shoggoth entries use plain bold: '<b>Deck Size</b>:'.
function investigator_back_label(label) {
    label = translate_tags(label);
    label = "<b>" + label.replace(/<\/hdr>/g, "</b>").replace(/<hdr>/g, "<b>") + "</b>:";
    return label.replace(/<b><\/b>/g, "");
}

// SE guide markup → shoggoth guide markdown (guide.py:markdown_to_html syntax)
function guide_text_to_markdown(text) {
    if (!text) return "";
    text = String(text);

    // framed boxes → ::: fenced blocks
    text = text.replace(/<boxres[^>]*>/g, "\n:::resolution\n");
    text = text.replace(/<boxsa[^>]*>/g, "\n:::standalone\n");
    text = text.replace(/<boxkey[^>]*>/g, "\n:::standalone\n");
    text = text.replace(/<boxint[^>]*>/g, "\n:::standalone\n");
    text = text.replace(/<boxfla[^>]*>/g, "\n:::story\n");
    text = text.replace(/<\/box(?:res|sa|key|int|fla)>/g, "\n:::\n");

    // guide headers
    text = text.replace(/<section[^>]*>([\s\S]*?)<\/section>/g, "\n## $1\n");
    text = text.replace(/<header[^>]*>([\s\S]*?)<\/header>/g, "\n### $1\n");

    // basic styling
    text = text.replace(/<\/?b>/g, "**");
    text = text.replace(/<\/?i>/g, "*");

    text = translate_tags(text);

    // SE treats every line as a paragraph; markdown needs blank lines
    var lines = text.split(/\n+/);
    var paras = [];
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line) paras.push(line);
    }
    return paras.join("\n\n");
}

function get_portraits(card) {
    let script_parts = card.getClassName().split("/");
    let script_name = script_parts[script_parts.length - 1];
    let bindings = PORTRAITS[script_name];
    if (!bindings) return null;
    let output = {};
    for (let i = 0; i < bindings.length; i++) {
        try{
            output[bindings[i]] = card.getPortrait(i);
        } catch (e){
            println("error in get_portraits", e);
        }
    }
    return output;
}

// SE draws a portrait at (image size × scale), centred on the middle of its
// clip region plus the pan offset. Shoggoth wants an absolute scale plus the
// top-left corner in template coordinates, so convert:
//   top-left = (clip centre + pan − scaled size / 2) × transform + bleed
// Returns { scale, pan_x, pan_y, rotation? } or null when the geometry can't
// be determined (no image, missing clip region, ...).
function portrait_geometry(card, portrait, transform) {
    try {
        let img = portrait.getImage();
        if (img == null) return null;
        let scale = portrait.getScale();
        if (!scale || scale <= 0) return null;

        // The clip region lives in the card settings under the portrait's
        // base key — the same lookup DefaultPortrait.paint() uses. Fall back
        // to stripped variants of the key in case it kept its
        // "-portrait-template" suffix.
        let base = String(portrait.getBaseKey());
        let candidates = [
            base,
            base.replace(/-portrait-template$/, ""),
            base.replace(/-template$/, ""),
        ];
        let clip = null;
        for (let i = 0; i < candidates.length && clip == null; i++) {
            try {
                clip = card.getSettings().getRegion(candidates[i] + "-portrait-clip");
            } catch (e) {}
        }
        if (clip == null) return null;

        let width = img.getWidth() * scale;
        let height = img.getHeight() * scale;
        let k = transform.scale;
        let geometry = {
            scale: Math.round(scale * k * 10000) / 10000,
            pan_x: Math.round((clip.getCenterX() + portrait.getPanX() - width / 2) * k) + transform.offset,
            pan_y: Math.round((clip.getCenterY() + portrait.getPanY() - height / 2) * k) + transform.offset,
        };
        try {
            // SE and shoggoth both treat positive angles as counter-clockwise
            let rotation = portrait.getRotation();
            if (rotation) geometry.rotation = Math.round(rotation * 100) / 100;
        } catch (e) {}
        return geometry;
    } catch (e) {
        return null;
    }
}

function apply_portrait_geometry(face, geometry) {
    if (!geometry) return;
    face["illustration_scale"] = geometry.scale;
    face["illustration_pan_x"] = geometry.pan_x;
    face["illustration_pan_y"] = geometry.pan_y;
    if (geometry.rotation) face["illustration_rotation"] = geometry.rotation;
}

function extract_images(card, collection, image_folder) {
    let script_parts = card.getClassName().split("/");
    let script_name = script_parts[script_parts.length - 1];
    let bindings = PORTRAITS[script_name];
    if (!bindings) return;
    for (let i = 0; i < bindings.length; i++) {
        try {
            let portrait = card.getPortrait(i);
            let source_raw = portrait.getSource();
            if (source_raw == null) continue;
            let source = String(source_raw);
            if (source == "") continue;
            if (source in collection.images) continue;
            collection.images[source] = "";

            let parts = source.replace(/\\/g, "/").split("/");
            let portrait_name = parts[parts.length - 1];
            let format_parts = portrait_name.split(".");
            let portrait_format = format_parts[format_parts.length - 1];

            let new_path = new File(image_folder, portrait_name);
            let counter = 0;
            while (new_path.exists()) {
                new_path = new File(image_folder, counter + "_" + portrait_name);
                counter++;
                if (counter > 35) {
                    println(
                        "ERROR: " +
                            card.getName() +
                            " failed to find suitable name for image " +
                            portrait_name,
                    );
                    break;
                }
            }
            collection.images[source] = "./images/" + new_path.getName();
            ImageIO.write(
                portrait.getImage(),
                portrait_format,
                new File(String(new_path)),
            );
        } catch (e){
            println("Failed to extract portrait", e);
        }
    }
}

function get_encounter_portrait_source(card) {
    let portraits = get_portraits(card);
    if (!portraits) return null;
    let titles = ["Encounter-Both", "Encounter-Front", "Encounter-Back"];
    for (let title of titles) {
        if (!(title in portraits)) continue;
        let source_raw = portraits[title].getSource();
        if (source_raw == null || String(source_raw) == "") continue;
        return String(source_raw);
    }
    return null;
}

// mirrors AHLCG-utilLibrary.js:createUserSettingValue
function user_setting_value(name) {
    return String(name).replace(/\W/g, "");
}

// Display name for a named set: plugin interface string, user-defined set
// name from preferences, or the raw key split on CamelCase as a last resort.
function encounter_set_display_name(set_key) {
    try {
        let lang = resources.Language.getInterface();
        if (lang.isKeyDefined("AHLCG-" + set_key)) {
            return String(lang.get("AHLCG-" + set_key));
        }
    } catch (e) {}
    try {
        let user = resources.Settings.getUser();
        let count = user.getInt("AHLCG-UserEncounterCount", 0);
        for (let i = 1; i <= count; i++) {
            let name = user.get("AHLCG-UserEncounterName" + i, "");
            if (name != "" && user_setting_value(name) == set_key) {
                return String(name);
            }
        }
    } catch (e) {}
    return String(set_key).replace(/([a-z0-9])([A-Z])/g, "$1 $2");
}

// "some_icon-file.png" → "some icon file"
function file_name_to_set_name(source) {
    let parts = source.replace(/\\/g, "/").split("/");
    let name = parts[parts.length - 1];
    name = name.replace(/\.[^.]+$/, "");
    name = name.replace(/^\d+_/, "");
    name = name.replace(/[-_]+/g, " ").trim();
    return name || "Encounter Set";
}

// Extract a plugin resource icon into the image folder (once) and return
// its project-relative path, or null when the resource doesn't exist.
function extract_resource_icon(set_key, collection, image_folder) {
    let res_path = "ArkhamHorrorLCG/icons/AHLCG-" + set_key + ".png";
    let cache_key = "res://" + res_path;
    if (cache_key in collection.images) return collection.images[cache_key];
    try {
        let url = resources.ResourceKit.composeResourceURL(res_path);
        if (url == null) return null;
        let image = ImageIO.read(url);
        if (image == null) return null;
        let out_file = new File(image_folder, "AHLCG-" + set_key + ".png");
        ImageIO.write(image, "png", out_file);
        collection.images[cache_key] = "./images/" + out_file.getName();
        return collection.images[cache_key];
    } catch (e) {
        println("Failed to extract set icon " + res_path + ": " + e);
        return null;
    }
}

// Whether this card actually shows its encounter set. Player-card scripts
// keep a leftover default 'Encounter' setting around, so mirror the exact
// conditions the plugin uses to draw the encounter icon.
function encounter_set_applies(script_name, settings) {
    if (script_name == "Event.js" || script_name == "Skill.js") {
        let cls = String(settings.get("CardClass") || "");
        return cls == "Story" || cls == "StoryWeakness";
    }
    if (script_name == "WeaknessEnemy.js" || script_name == "WeaknessTreachery.js") {
        return String(settings.get("Subtype") || "") == "StoryWeakness";
    }
    // otherwise: encounter-capable iff the card type has an Encounter portrait slot
    let bindings = PORTRAITS[script_name] || [];
    for (let i = 0; i < bindings.length; i++) {
        if (bindings[i].indexOf("Encounter") === 0) return true;
    }
    return false;
}

// SE marks a card's encounter set in two ways: the plugin's set feature
// (the 'Encounter' card setting: a standard NameKey or a sanitized
// user-defined set name) or — for 'CustomEncounterSet' — just the image
// loaded into the Encounter portrait slot. Group by the named set when
// there is one, by the portrait source path otherwise.
function determine_encounter_set(card, settings, script_name) {
    if (!encounter_set_applies(script_name, settings)) return null;
    let encounter = has_value(settings.get("Encounter"));
    if (encounter && String(encounter) != "CustomEncounterSet") {
        let set_key = String(encounter);
        return {
            key: "set:" + set_key,
            name: encounter_set_display_name(set_key),
            resource_key: set_key,
            portrait_source: get_encounter_portrait_source(card),
        };
    }
    let source = get_encounter_portrait_source(card);
    if (source) {
        return {
            key: "img:" + source,
            name: file_name_to_set_name(source),
            resource_key: null,
            portrait_source: source,
        };
    }
    return null;
}

// User-defined sets keep their icon path in the user preferences; cards saved
// before the plugin copied that icon into the Encounter portrait slot have an
// empty portrait, so pull the file straight from the preference.
function extract_user_encounter_icon(set_key, collection, image_folder) {
    try {
        let user = resources.Settings.getUser();
        let count = user.getInt("AHLCG-UserEncounterCount", 0);
        for (let i = 1; i <= count; i++) {
            let name = user.get("AHLCG-UserEncounterName" + i, "");
            if (name == "" || user_setting_value(name) != set_key) continue;
            let icon_path = String(user.get("AHLCG-UserEncounterIcon" + i, ""));
            if (icon_path == "") return null;
            let cache_key = "file://" + icon_path;
            if (cache_key in collection.images) return collection.images[cache_key];
            let source_file = new File(icon_path);
            if (!source_file.exists()) return null;
            let image = ImageIO.read(source_file);
            if (image == null) return null;
            let out_file = new File(image_folder, "set_" + set_key + ".png");
            ImageIO.write(image, "png", out_file);
            collection.images[cache_key] = "./images/" + out_file.getName();
            return collection.images[cache_key];
        }
    } catch (e) {}
    return null;
}

// The collection (pack) icon works like the encounter set: the 'Collection'
// setting names a standard pack (plugin resource icon) or a user-defined
// collection, and 'CustomCollection' means the image in the Collection
// portrait slot. Shoggoth has one icon per project, so each card reports its
// collection identity here and process() only sets the project icon when
// every card agrees.
function determine_collection_icon(card, settings, script_name) {
    let bindings = PORTRAITS[script_name] || [];
    let portrait_index = -1;
    for (let i = 0; i < bindings.length; i++) {
        if (bindings[i].indexOf("Collection") === 0) portrait_index = i;
    }
    if (portrait_index < 0) return null;

    let coll = has_value(settings.get("Collection"));
    if (coll && String(coll) != "CustomCollection") {
        return { key: "set:" + String(coll), resource_key: String(coll), portrait_source: null };
    }
    try {
        let source = card.getPortrait(portrait_index).getSource();
        if (source != null && String(source) != "") {
            return { key: "img:" + String(source), resource_key: null, portrait_source: String(source) };
        }
    } catch (e) {}
    return null;
}

function register_encounter_set(out, card, settings, script_name, collection, image_folder) {
    let encounter = determine_encounter_set(card, settings, script_name);
    if (!encounter) return;

    if (!collection.encounter_sets[encounter.key]) {
        let icon = null;
        if (encounter.resource_key) {
            icon = extract_resource_icon(encounter.resource_key, collection, image_folder);
        }
        if (!icon && encounter.portrait_source) {
            // portrait images were already extracted by extract_images
            icon = collection.images[encounter.portrait_source] || encounter.portrait_source;
        }
        if (!icon && encounter.resource_key) {
            icon = extract_user_encounter_icon(encounter.resource_key, collection, image_folder);
        }
        collection.encounter_sets[encounter.key] = {
            name: encounter.name,
            icon: icon || "",
            id: java.util.UUID.randomUUID().toString(),
            card_amount: 0,
        };
    }
    let es = collection.encounter_sets[encounter.key];
    out["encounter_set"] = es.id;

    // card_amount: trust the largest EncounterTotal the set's cards declare,
    // fall back to counting converted cards
    es._count = (es._count || 0) + 1;
    let total = parseInt(has_value(settings.get("EncounterTotal")) || "0") || 0;
    es.card_amount = Math.max(es.card_amount, total, es._count);
}

function has_value(val){
    if (val == null || val == "" || val == "None"){
        return false;
    }
    return val;
}

function convert_card(path, collection, image_folder) {
    let card = ResourceKit.getGameComponentFromFile(new File(path), false);
    if (!card) {
        println("ERROR: " + path + " appears to have issues loading.");
        return;
    }
    let script_parts = card.getClassName().split("/");
    let script_name = script_parts[script_parts.length - 1];
    if (!(script_name in front_types) && !(script_name in back_types)) {
        return;
    }
    let settings = card.getSettings();
    let out = {
        id: java.util.UUID.randomUUID().toString(),
    };

    println("processing " + path);

    extract_images(card, collection, image_folder);

    // name
    if (card.getFullName() != "") {
        out["name"] = card.getFullName();
    } else {
        let file_parts = path.replace("\\", "/").split("/");
        out["name"] = file_parts[file_parts.length - 1];
    }

    // front/back types
    out["front"] = {
        type: front_types[script_name],
    };
    out["back"] = {
        type: back_types[script_name],
    };

    // unique
    if (has_value(settings.get("Unique")) && settings.get("Unique") != "0") {
        out["front"]["title"] = "<unique><name>";
    }

    // subtitle
    if (has_value(settings.get("Subtitle"))) {
        out["front"]["subtitle"] = settings.get("Subtitle");
    }

    // traits
    if (has_value(settings.get("Traits"))) {
        out["front"]["traits"] = settings.get("Traits");
    }

    // text (keywords + rules)
    if (has_value(settings.get("Rules")) && has_value(settings.get("Keywords"))) {
        out["front"]["text"] = settings.get("Keywords") + "\n" + settings.get("Rules");
    } else if (has_value(settings.get("Rules")) || has_value(settings.get("Keywords"))) {
        out["front"]["text"] = has_value(settings.get("Keywords")) || has_value(settings.get("Rules"));
    }

    // cost / level / slot
    if (has_value(settings.get("ResourceCost")))
        out["front"]["cost"] = String(settings.get("ResourceCost")).replace("-", "<dash>");
    // "None" is a real level (card without a level, distinct from level 0 —
    // shoggoth defaults level to 0 when the key is missing), so unlike other
    // fields it must survive the None-scrubbing.
    let level = settings.get("Level");
    if (level != null && String(level) !== "")
        out["front"]["level"] = String(level);
    if (has_value(settings.get("Slot"))) {
        let slots = [String(settings.get("Slot"))];
        if (has_value(settings.get("Slot2"))) {
            slots.push(String(settings.get("Slot2")))
        };
        out["front"]["slot"] = slots.join(", ");
    }

    // health / sanity / evade / combat
    let health = has_value(settings.get("Health")) || has_value(settings.get("Stamina"));
    if (health) {
        out["front"]["health"] =
            String(health) + ((settings.get("PerInvestigator") == "1" || settings.get("PerInvestigatorStamina") == "1") ? "<per>" : "");
    }
    if (has_value(settings.get("Sanity"))) {
        out["front"]["sanity"] = String(settings.get("Sanity")).replace("-", "<dash>") +
            (settings.get("PerInvestigatorSanity") == "1" ? "<per>" : "");
    }
    if (has_value(settings.get("Evade"))) {
        out["front"]["evade"] = String(settings.get("Evade")).replace("-", "<dash>") +
            (settings.get("PerInvestigatorEvade") == "1" ? "<per>" : "");
    }
    if (has_value(settings.get("Attack"))) {
        out["front"]["combat"] = String(settings.get("Attack")).replace("-", "<dash>") +
            (settings.get("PerInvestigatorAttack") == "1" ? "<per>" : "");
    }

    // damage / horror
    if (has_value(settings.get("Damage")))
        out["front"]["damage"] = parseInt(settings.get("Damage"));
    if (has_value(settings.get("Horror")))
        out["front"]["horror"] = parseInt(settings.get("Horror"));

    // flavor text
    let flavor =
        has_value(settings.get("AgendaStory")) ||
        has_value(settings.get("ActStory")) ||
        has_value(settings.get("Flavor"));
    if (flavor) {
        out["front"]["flavor_text"] = flavor;
    }

    // victory
    if (has_value(settings.get("Victory"))) {
        out["front"]["victory"] = settings.get("Victory");
    }
    // victory
    if (has_value(settings.get("VictoryBack"))) {
        out["back"]["victory"] = settings.get("VictoryBack");
    }

    // classes
    if (has_value(settings.get("CardClass"))) {
        out["front"]["classes"] = [];
        let class_keys = ["CardClass", "CardClass2", "CardClass3"];
        for (let key of class_keys) {
            let cl = has_value(settings.get(key));
            if (cl) {
                out["front"]["classes"].push(String(cl).toLowerCase());
            }
        }
    }
    
    // subtype (for weakness cards)
    if (has_value(settings.get("Subtype"))){
        out["front"]["classes"] = out["front"]["classes"] || [];
        out["front"]["classes"].push(String(settings.get("Subtype")).toLowerCase().replace("basicweakness", "basic weakness"));
    }

    // investigator skills (only Investigator*.js define these settings)
    if (has_value(settings.get("Willpower")))
        out["front"]["willpower"] = String(settings.get("Willpower"));
    if (has_value(settings.get("Intellect")))
        out["front"]["intellect"] = String(settings.get("Intellect"));
    if (has_value(settings.get("Combat")))
        out["front"]["combat"] = String(settings.get("Combat"));
    if (has_value(settings.get("Agility")))
        out["front"]["agility"] = String(settings.get("Agility"));

    // investigator back: deckbuilding entries (Text1..8NameBack / Text1..8Back)
    if (out["back"]["type"] === "investigator_back") {
        let inv_entries = [];
        for (let i = 1; i <= 8; i++) {
            let label = has_value(settings.get("Text" + i + "NameBack"));
            let value = has_value(settings.get("Text" + i + "Back"));
            if (!label && !value) continue;
            inv_entries.push([
                label ? investigator_back_label(String(label)) : "",
                value ? translate_text(String(value)) : "",
            ]);
        }
        if (inv_entries.length > 0) {
            out["back"]["entries"] = inv_entries;
            // shoggoth's renderer reads the joined "label value" lines from
            // "text"; "entries" only feeds the editor fields (see
            // investigator_editors.py:on_entries_changed)
            let text_parts = [];
            for (let entry of inv_entries) {
                if (entry[0] && entry[1]) text_parts.push(entry[0] + " " + entry[1]);
            }
            if (text_parts.length > 0) {
                out["back"]["text"] = text_parts.join("\n");
            }
        }
    }

    // skill icons (Skill1-Skill6, values: Willpower/Intellect/Combat/Agility/Wild/None)
    let skill_icon_map = {
        "Willpower": "W",
        "Intellect": "I",
        "Combat": "C",
        "Agility": "A",
        "Wild": "Q",
    };
    let icons = "";
    for (let i = 1; i <= 6; i++) {
        let skill = has_value(settings.get("Skill" + i));
        if (skill && skill_icon_map[String(skill)]) {
            icons += skill_icon_map[String(skill)];
        }
    }
    if (icons) {
        out["front"]["icons"] = icons;
    }

    // illustrations from portraits, keeping SE's placement and scale
    let illustrations = get_portraits(card);
    if (illustrations) {
        for (let name in illustrations) {
            let portrait = illustrations[name];
            if (portrait.getSource() == null) continue;
            let image_path = collection.images[String(portrait.getSource())];
            if (!image_path) continue;
            let transform = GEOMETRY_TRANSFORM[script_name] || GEOMETRY_DEFAULT_TRANSFORM;
            let geometry = GEOMETRY_SKIP[script_name]
                ? null
                : portrait_geometry(card, portrait, transform);
            if (
                name === "Portrait-Front" ||
                name === "Portrait-Both" ||
                name === "TransparentPortrait-Both"
            ) {
                out["front"]["illustration"] = image_path;
                apply_portrait_geometry(out["front"], geometry);
            }
            if (
                name === "Portrait-Back" ||
                name === "Portrait-Both" ||
                name === "BackPortrait-Back" ||
                name === "TransparentPortrait-Both"
            ) {
                out["back"]["illustration"] = image_path;
                apply_portrait_geometry(out["back"], geometry);
            }
        }
    }

    // clues
    if (has_value(settings.get("Clues"))) {
        out["front"]["clues"] =
            settings.get("Clues").replace("-", "<dash>") +
            (settings.get("PerInvestigator") == "1" ? "<per>" : "");
    }

    // shroud
    if (has_value(settings.get("Shroud"))) {
        out["front"]["shroud"] =
            settings.get("Shroud", "").replace("-", "<dash>") +
            (settings.get("ShroudPerInvestigator") == "1" ? "<per>" : "");
    }

    // doom
    if (has_value(settings.get("Doom"))) {
        out["front"]["doom"] =
            settings.get("Doom").replace("-", "<dash>") +
            (settings.get("PerInvestigator") == "1" ? "<per>" : "");
    }

    // scenario index
    if (has_value(settings.get("ScenarioIndex"))) {
        let deck_id = has_value(settings.get("ScenarioDeckID"));
        out["front"]["index"] =
            String(settings.get("ScenarioIndex")) + (deck_id ? String(deck_id) : "");
    }

    // location icon
    if (has_value(settings.get("LocationIcon"))) {
        out["front"]["connection"] = String(
            settings.get("LocationIcon"),
        ).toLowerCase();
    }

    // connections
    let connections = [];
    for (let i = 1; i <= 6; i++) {
        let c = has_value(settings.get("Connection" + i + "Icon"));
        if (c) {
            connections.push(String(c).toLowerCase());
        }
    }
    if (connections.length > 0) {
        out["front"]["connections"] = connections;
    }

    // encounter / collection numbers
    if (has_value(settings.get("EncounterNumber"))) {
        out["encounter_number"] = settings.get("EncounterNumber");
        // a range like "3-4" means the set holds that many copies
        let range = /^(\d+)\s*-\s*(\d+)$/.exec(String(settings.get("EncounterNumber")));
        if (range) {
            let amount = parseInt(range[2]) - parseInt(range[1]) + 1;
            if (amount > 1) out["amount"] = amount;
        }
    }
    if (has_value(settings.get("CollectionNumber"))) {
        out["project_number"] = settings.get("CollectionNumber");
    }

    // artist
    if (has_value(settings.get("Artist"))) {
        out["front"]["illustrator"] = "Illus. " + String(settings.get("Artist"));
    }
    if (has_value(settings.get("ArtistBack"))) {
        out["back"]["illustrator"] = "Illus. " + String(settings.get("ArtistBack"));
    }

    // back side fields
    if (has_value(settings.get("TitleBack"))) {
        out["back"]["name"] = String(settings.get("TitleBack"));
    }
    if (has_value(settings.get("SubtitleBack"))) {
        out["back"]["subtitle"] = String(settings.get("SubtitleBack"));
    }
    if (has_value(settings.get("TraitsBack"))) {
        out["back"]["traits"] = settings.get("TraitsBack");
    }
    if (has_value(settings.get("RulesBack")) && has_value(settings.get("KeywordsBack"))) {
        out["back"]["text"] =
            String(settings.get("KeywordsBack")) +
            "\n" +
            String(settings.get("RulesBack"));
    } else if (has_value(settings.get("RulesBack")) || has_value(settings.get("KeywordsBack"))) {
        out["back"]["text"] =
            has_value(settings.get("KeywordsBack")) || has_value(settings.get("RulesBack"));
    }
    if (has_value(settings.get("FlavorBack"))) {
        out["back"]["flavor_text"] = settings.get("FlavorBack");
    }
    if (has_value(settings.get("VictoryBack"))) {
        out["back"]["victory"] = settings.get("VictoryBack");
    }
    if (has_value(settings.get("ShroudBack"))) {
        out["back"]["shroud"] =
            settings.get("ShroudBack", "").replace("-", "<dash>") +
            (settings.get("ShroudPerInvestigatorBack") == "1" ? "<per>" : "");
    }
    if (has_value(settings.get("CluesBack"))) {
        out["back"]["clues"] =
            settings.get("CluesBack").replace("-", "<dash>") +
            (settings.get("PerInvestigatorBack") == "1" ? "<per>" : "");
    }

    // back location icon
    let backLocIcon = has_value(settings.get("LocationIconBack"));
    if (backLocIcon) {
        if (String(backLocIcon) === "Copy front") {
            out["back"]["connection"] = "<copy>";
        } else if (String(backLocIcon) !== "None") {
            out["back"]["connection"] = String(backLocIcon).toLowerCase();
        }
    }

    // back connections: only set ("None") entries count; all-copies → <copy>
    let back_connections = [];
    let back_conn_count = 0;
    let copy_count = 0;
    for (let i = 1; i <= 6; i++) {
        let c = has_value(settings.get("Connection" + i + "IconBack"));
        if (!c) continue;
        back_conn_count++;
        if (String(c) === "Copy front") {
            copy_count++;
            continue;
        }
        back_connections.push(String(c).toLowerCase());
    }
    if (back_conn_count > 0 && copy_count === back_conn_count) {
        out["back"]["connections"] = "<copy>";
    } else if (back_connections.length > 0) {
        out["back"]["connections"] = back_connections;
    }

    // back skill icons
    let back_icons = "";
    for (let i = 1; i <= 6; i++) {
        let skill = has_value(settings.get("Skill" + i + "Back"));
        if (skill && skill_icon_map[String(skill)]) {
            back_icons += skill_icon_map[String(skill)];
        }
    }
    if (back_icons != "") {
        out["back"]["icons"] = back_icons;
    }

    // back unique
    if (settings.get("UniqueBack") == "1")  {
        out["back"]["title"] = "<unique><name>";
    }

    // back enemy stats
    let health_back = has_value(settings.get("HealthBack")) || has_value(settings.get("StaminaBack"));
    if (health_back)
        out["back"]["health"] =
            String(health_back) +
            (settings.get("PerInvestigatorBack") == "1" ? "<per>" : "");
    if (has_value(settings.get("SanityBack"))){
        out["back"]["sanity"] = settings.get("SanityBack");
    }
    if (has_value(settings.get("AttackBack")))
        out["back"]["combat"] =
            String(settings.get("AttackBack")) +
            (settings.get("PerInvestigatorAttackBack") == "1" ? "<per>" : "");
    if (has_value(settings.get("EvadeBack")))
        out["back"]["evade"] =
            String(settings.get("EvadeBack")) +
            (settings.get("PerInvestigatorEvadeBack") == "1" ? "<per>" : "");
    if (has_value(settings.get("DamageBack")))
        out["back"]["damage"] = parseInt(settings.get("DamageBack"));
    if (has_value(settings.get("HorrorBack")))
        out["back"]["horror"] = parseInt(settings.get("HorrorBack"));

    // back asset stats
    if (has_value(settings.get("ResourceCostBack")))
        out["back"]["cost"] = String(settings.get("ResourceCostBack"));
    if (has_value(settings.get("CardClassBack"))) {
        out["back"]["classes"] = [
            String(settings.get("CardClassBack")).toLowerCase(),
        ];
    }
    if (has_value(settings.get("SlotBack"))) {
        out["back"]["slot"] = String(settings.get("SlotBack"));
    }

    // structured act/agenda back text (HeaderA/B/C + AccentedStoryA/B/C + RulesA/B/C)
    if (
        has_value(settings.get("HeaderABack")) ||
        has_value(settings.get("AccentedStoryABack")) ||
        has_value(settings.get("RulesABack"))
    ) {
        let parts = [];
        let sections = ["A", "B", "C"];
        for (let s of sections) {
            let header = has_value(settings.get("Header" + s + "Back"));
            let story = has_value(settings.get("AccentedStory" + s + "Back"));
            let rules = has_value(settings.get("Rules" + s + "Back"));
            if (header) parts.push(String(header));
            if (story) parts.push(String(story));
            if (rules) parts.push(String(rules));
        }
        if (parts.length > 0) {
            out["back"]["text"] = parts.join("\n");
        }
    }

    // chaos card entries
    if (front_types[script_name] === "chaos") {
        let token_map = {
            Skull: "skull",
            Cultist: "cultist",
            Tablet: "tablet",
            ElderThing: "elder_thing",
        };
        let merge_keys = {
            Skull: "MergeSkull",
            Cultist: "MergeCultist",
            Tablet: "MergeTablet",
        };

        // front entries
        let front_entries = [];
        for (let token_name in token_map) {
            let text = has_value(settings.get(token_name));
            if (text) {
                let token = token_map[token_name];
                let merge_key = merge_keys[token_name];
                if (merge_key) {
                    let merge_val = settings.get(merge_key);
                    if (merge_val && String(merge_val) !== "None") {
                        token = token + "," + token_map[String(merge_val)];
                    }
                }
                front_entries.push({ token: token, text: String(text) });
            }
        }
        out["front"]["entries"] = front_entries;

        // back entries
        let back_entries = [];
        for (let token_name in token_map) {
            let text = has_value(settings.get(token_name + "Back"));
            if (text) {
                let token = token_map[token_name];
                let merge_key = merge_keys[token_name];
                if (merge_key) {
                    let merge_val = settings.get(merge_key + "Back");
                    if (merge_val && String(merge_val) !== "None") {
                        token = token + "," + token_map[String(merge_val)];
                    }
                }
                back_entries.push({ token: token, text: String(text) });
            }
        }
        out["back"]["entries"] = back_entries;
        out["back"]["difficulty"] = "Hard/Expert";
    }

    // encounter set
    register_encounter_set(out, card, settings, script_name, collection, image_folder);

    // collector number (<exn> on the card's collection line)
    if (has_value(settings.get("CollectionNumber"))) {
        let project_number = parseInt(String(settings.get("CollectionNumber")));
        if (!isNaN(project_number)) out["project_number"] = project_number;
    }

    // report the card's collection identity for the project icon vote
    let collection_icon = determine_collection_icon(card, settings, script_name);
    if (collection_icon) {
        collection._collection_icons[collection_icon.key] = collection_icon;
    }

    // translate text fields to shoggoth syntax
    let sides = [out["front"], out["back"]];
    for (let side of sides) {
        if (side["text"]) side["text"] = translate_text(side["text"]);
        if (side["flavor_text"])
            side["flavor_text"] = translate_text(side["flavor_text"]);
        if (side["entries"]) {
            for (let entry of side["entries"]) {
                // chaos entries are {token, text}; investigator-back entries
                // are [label, value] arrays and already translated
                if (entry.text) entry.text = translate_text(entry.text);
            }
        }
    }

    collection.cards.push(out);
}

function convert_guide_page(path, collection, image_folder) {
    var card = ResourceKit.getGameComponentFromFile(new File(path), false);
    if (!card) return null;
    var script_parts = card.getClassName().split("/");
    var script_name = script_parts[script_parts.length - 1];
    if (!(script_name in GUIDE_SCRIPTS)) return null;

    println("processing guide page: " + path);

    extract_images(card, collection, image_folder);

    var settings = card.getSettings();
    var page = {};
    page.format = GUIDE_SCRIPTS[script_name];
    page.name = String(card.getFullName() || "");
    page.page_num = parseInt(String(settings.get("Page") || "0")) || 0;
    page.page_type = String(settings.get("PageType") || "");
    page.rules_left = String(settings.get("RulesLeft") || "");
    page.rules_right = String(settings.get("RulesRight") || "");
    page.position1 = String(settings.get("PositionPortrait1") || "None");
    page.position2 = String(settings.get("PositionPortrait2") || "None");

    var portraits = get_portraits(card);
    if (portraits) {
        var p1 = portraits["Portrait1-Front"];
        var p2 = portraits["Portrait2-Front"];
        if (p1 && p1.getSource() != null) {
            page.image1 = collection.images[String(p1.getSource())] || null;
        }
        if (p2 && p2.getSource() != null) {
            page.image2 = collection.images[String(p2.getSource())] || null;
        }
    }

    return page;
}

// position option → shoggoth :::image-* block type ('top'/'bottom'/'block')
function image_block_type(position) {
    var pos = String(position).toLowerCase();
    if (pos == "none") return null;
    if (pos.indexOf("bottom") === 0) return "bottom";
    if (pos.indexOf("top") === 0) return "top";
    return "block"; // LeftLarge / RightLarge / FullPage
}

function image_block_markdown(src, block_type) {
    return ":::image-" + block_type + "\n" + src + "\n:::";
}

// One SE guide page → one shoggoth guide section (blank chapter).
// Shoggoth chapters auto-flow two columns, so SE's explicit left/right
// column texts are simply concatenated and left to reflow.
function guide_page_to_section(page, index) {
    var parts = [];

    if (page.page_type == "Title" && page.name) {
        parts.push("# " + page.name);
    }

    var images = [
        { src: page.image1, type: page.image1 ? image_block_type(page.position1) : null },
        { src: page.image2, type: page.image2 ? image_block_type(page.position2) : null },
    ];

    for (var i = 0; i < images.length; i++) {
        if (images[i].type && images[i].type != "bottom") {
            parts.push(image_block_markdown(images[i].src, images[i].type));
        }
    }

    var body = guide_text_to_markdown(page.rules_left);
    var body_right = guide_text_to_markdown(page.rules_right);
    if (body && body_right) body += "\n\n" + body_right;
    else body = body || body_right;
    if (body) parts.push(body);

    for (var i = 0; i < images.length; i++) {
        if (images[i].type == "bottom") {
            parts.push(image_block_markdown(images[i].src, "bottom"));
        }
    }

    // section name: page title, first <section> header, or the page number
    var name = page.name;
    if (!name) {
        var header = /^## (.*)$/m.exec(body || "");
        name = header ? header[1] : "Page " + (page.page_num || index + 1);
    }

    return {
        id: java.util.UUID.randomUUID().toString().slice(0, 8),
        type: "blank",
        name: name,
        markdown: parts.join("\n\n"),
    };
}

function build_guide(guide_pages) {
    guide_pages.sort(function (a, b) {
        if (a.page_num != b.page_num) return a.page_num - b.page_num;
        // title page first when page numbers tie
        return (a.page_type == "Title" ? 0 : 1) - (b.page_type == "Title" ? 0 : 1);
    });

    // majority vote on the paper size when page components disagree
    var format_votes = {};
    var format = "a4";
    var best = 0;
    for (var i = 0; i < guide_pages.length; i++) {
        var f = guide_pages[i].format;
        format_votes[f] = (format_votes[f] || 0) + 1;
        if (format_votes[f] > best) {
            best = format_votes[f];
            format = f;
        }
    }

    var name = "Guide";
    for (var i = 0; i < guide_pages.length; i++) {
        if (guide_pages[i].page_type == "Title" && guide_pages[i].name) {
            name = guide_pages[i].name;
            break;
        }
    }

    var sections = [];
    for (var i = 0; i < guide_pages.length; i++) {
        sections.push(guide_page_to_section(guide_pages[i], i));
    }

    return {
        id: java.util.UUID.randomUUID().toString(),
        name: name,
        format: format,
        sections: sections,
    };
}

function process(progress) {
    let cards = [];
    Files.walk(Paths.get(PROJECT.getFile().getPath())).forEach(function (card) {
        let path = card.toString();
        if (
            path.slice(-4) === ".eon" &&
            card.getFileName().toString() !== "deck.eon"
        ) {
            cards.push(path);
            println(card);
        }
    });
    println("Processing " + cards.length + " cards");

    let collection = {
        name: PROJECT.getFile().getName(),
        encounter_sets: {},
        cards: [],
        images: {},
        _collection_icons: {},
    };

    let guide_pages = [];
    for (let path of cards) {
        let guide_page = convert_guide_page(path, collection, IMAGE_FOLDER);
        if (guide_page !== null) {
            guide_pages.push(guide_page);
        } else {
            convert_card(path, collection, IMAGE_FOLDER);
        }
    }

    println("Done processing cards. Post processing begins...");

    // project icon: set it only when every card names the same collection —
    // a mixed-collection SE project has no single shoggoth project icon
    let collection_icon_keys = Object.keys(collection._collection_icons);
    if (collection_icon_keys.length === 1) {
        let ci = collection._collection_icons[collection_icon_keys[0]];
        let icon = null;
        if (ci.resource_key) {
            icon = extract_resource_icon(ci.resource_key, collection, IMAGE_FOLDER);
        }
        if (!icon && ci.portrait_source) {
            icon = collection.images[ci.portrait_source] || null;
        }
        if (icon) collection.icon = icon;
    }
    delete collection._collection_icons;

    // convert encounter_sets from dict to array, resolve icon paths
    let encounter_set_list = [];
    for (let key in collection.encounter_sets) {
        let es = collection.encounter_sets[key];
        if (collection.images[es.icon]) {
            es.icon = collection.images[es.icon];
        }
        delete es._count;
        encounter_set_list.push(es);
    }
    collection.encounter_sets = encounter_set_list;
    delete collection.images;

    // Convert guide pages into a shoggoth guide (markdown sections)
    if (guide_pages.length > 0) {
        println("Converting " + guide_pages.length + " guide pages...");
        collection.guides = [build_guide(guide_pages)];
    }

    OUTPUT_FILE.createNewFile();
    // FileWriter would use the platform charset (windows-1252 on Windows) and
    // mangle special characters — shoggoth reads project.json as UTF-8.
    let writer = new java.io.OutputStreamWriter(
        new java.io.FileOutputStream(OUTPUT_FILE),
        "UTF-8",
    );
    writer.write(JSON.stringify(collection, null, 4));
    writer.close();
    println("Done writing to " + String(OUTPUT_FILE));
}

Thread.busyWindow(process, "Building...", true);
