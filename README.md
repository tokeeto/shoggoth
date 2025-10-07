# Shoggoth
## Card creation software for Arkham Horror: The Card Game

## Status
Under development. Viewermode probably out of date. Lots of stuff has only been implemented with surface level functionality or only works with specific setups.

Shoggoth allows you to create homebrew cards for Arkham Horror: The Card Game. It features a sensible templating system with inheritance, that makes it easy to define new cards in very few rules.

## Installation:
**Recommended**
It's recommended to install Shoggoth as a python tool. If this scares you, check out the "easy" option below.
1. Install [python](https://python.org).
2. Install Shoggoth as a python tool, using `pipx install shoggoth` (or `uvx shoggoth` if you use uv). 

**Easy installation**
1. Download the build for releases for your system.
2. Run the application.
Note, that due to this being a hobby project, I'm not going to spend resources on obtaining a Apple developer license, and as such, Mac will complain about the application being unsigned, insecure or unknown. That is expected.

**Security and false positives in virus detection**
Windows defender has on ocassion reported Shoggoth as being harmful.
Shoggoth is not malware, but it does a lot of the same things as malware - it downloads files from the internet without asking you (asset files), unpacks them, and parse arbitrary files (projects/cards) on your system.
All of this is intended and expected. That being said, Shoggoth is not reviewed for security, and you shouldn't try to run files from people you don't trust. I can't give you any guarantee that the standard python json module doesn't have some exploit, that will allow someone take over your system. Most software can't make that guarantee.

## Usage
You can either start Shoggoth in UI mode using `shoggoth`, or you can run it in "viewer mode" using `shoggoth -v path/to/project_file.json`.
In UI mode, you'll have an experience similar to other card designers, where the UI will help guide you along to create cards similar to official cards.
In viewer mode, you can use your favorite json/text editor to edit the project file, and the viewer will refresh on each and every file save, while jumping straight to first detected change - effectively showing you the card you're working on, live while you write it.

## Card and data design
Shoggoth is built for Arkham Horror: The Card Game (trademarked by Fantasy Flight Games. No affiliation, nor endorsement whatsoever).
In theory, there's only 7 card types in AHTCG, but over time, there has been so many variations and exceptions. This has led to Shoggoth adopting the following design:

All Cards are contained within a Project, or Expansion - the two terms will be used interchangably. Technically, and expansion signifies a big project, whereas a project could be a small set of 1 to 4 cards, but in technical terms it's the same thing.

A Project can have cards directly or Encounter Sets that contain cards. Player cards will typically belong directly to an expansion, whereas encounter cards are grouped by Encounter Sets.

All Cards are built from some standard information, and 2 Faces, the front and back. All faces are identical in fields - there's no feature available for one face that's not available for every other. Enemies can have Shroud, Clues, Doom, and locations can have Attack, Health and Horror.
The UI makes it easy to generate standard compliant cards, but if you edit the json data directly, you have full control.

### Structure and Fields
Project
```json
{
    "name": "Full Name of Project",
    "icon": "path/to/icon.jpeg",
    "code": "FNoP",
    "encounter_sets": [],
    "cards": [],
    "id": "random-generated-guid"
}```

Encounter Set
```json
{
    "name": "Name of Set",
    "icon": "path/to/encounter/icon.png",
    "code": "NoS",  // Shorthand code for set
    "card_amount": 40,  // automatically calculated, stored for convinience
    "id": "random-generated-guid",
    "order": 1  // manual order, such as scenario order, in the expansion
}```

Cards
```json
{
    "name": "Werewolf",  // Primary name of card. The actual title text on the card can be different, but this is the identifier. 
    "front": {},  // Front side of the card.
    "back": {},
    "encounter_number": "10",  // Number in the encounter set, if any. This can be given as a range "10-15" or a single number.
    "expansion_number": 50,  // Card number in the expansion.
    "id": "0a1b2a69-b55f-4571-8b20-90eaa2fea43b",  // random guid
    "encounter_set": "c959bdf0-6833-4e10-b1ee-7af118b18f15",  // id of the containing encounter set.
    "investigator": "Astrid"  // Mainly for player cards - used for grouping cards related to an investigator, such as signatures and weakness together with the investigator.
}
```

Faces
```json
{
    "type": "enemy",  // Which template should be used. This either references one of the defaults in the asset package, or a file location of your json templte.
    "text": "",  // Main body text of the card.
    "flavor_text": "",  // Flavor text, background story, etc, all goes here.
    "traits": "Monster.", // Traits of the card  
    "victory": "Victory 1.",  // The victory field
    "illustration": "/path/to/werewolf.png", // path to the primary image for this card. 
    "health": "5<per>", // health of this card.
    "evade": "5",  // evasion value of this card
    "attack": "3", // attack value
    "damage": 1,  // number of damage per attack
    "horror": 2,  // number of horror per attack
    "classes": [] // variation of this card. For enemies this can be ["weakness"] or ["basic_weakness"], for assets it could be ["seeker", "guardian"].
}
```

Many more fields are available. Almost all fields are text fields, and takes a string to render. A few are intergers, lists or file paths. The full specification will be available later. Check out the defaults in the asset package. 

You can incentivise the further development of Shoggoth (and other AH:TCG software and content) by donating on [Patreon](https://patreon.com/tokeeto) or [Ko-Fi](https://ko-fi.com/tokeeto).
