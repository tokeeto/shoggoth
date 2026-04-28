# Shoggoth Manual

## TOC
- [What is Shoggoth?](#what-is-shoggoth)
- Installation
- Using Shoggoth
 - The UI and General Concepts
 - Creating a project
 - Creating player cards
 - Creating scenario cards
 - Exporting
- Organization of files
- Sharing and workflows
- Translating projects

## What is Shoggoth? {#what-is-shoggoth}
Shoggoth is an application for creating custom cards and related content for Arkham Horror: The Card Game by Fantasy Flight Games.

Shoggoth is not affiliated with, nor endorsed by Fantasy Flight Games.

## Installation {#installation}
To install Shoggoth, either go to the [releases page](link to releases), install the python package or clone this repo.

### Building Shoggoth
If you're interrested in building and/or developing Shoggoth yourself, here's how:

- Install [uv](https://docs.astral.sh/uv/)
 - Alternatively you _can_ use pip, but you'd have to install the requirements listed in the pyproject.toml file yourself. There's not a lot though. 
- Clone this repo
- `uv run ./shoggoth`

Shoggoth has a sister repo on on [shoggoth-assets](https://github.com/tokeeto/shoggoth_assets) that you might want to take a look at. But it's automatically downloaded when running Shoggoth, so unless you want to fix something specifically in that repo, there's no need to clone that one as well.

# Using Shoggoth

## General Concepts
Shoggoth uses a heirachial model that is very reminicent of how Arkham Horror products are sold and organized. 

- Project: This is what would generally be called "an expansion". That can be a single scenario pack, an investigator expansion, a campaign expansion, or any other grouped "product".
- Encounter set: This is an encounter set within an expansion. This is used to group and number encounter cards, and has an icon shared between cards within.
- Card: A single card consisting of a front and a back Face.
- Face: A single side of a card. This could be anything from the generic player card background to the front of an investigator card.
- Type: A set of default values (including images) for a Face. This is typically something like "investigator front" or "Location Back". But could also be very custom, such as "MyReturningVillain.json".

From this, you might be able to see, that there is no inherent built-in card types in Shoggoth. Everything is just Cards with Faces with predefined defaults, but everything can be overwritten. This makes Shoggoth very easy to work with if you got unique ideas.

## The UI
Shoggoth generally has 3 places to find commands: In the menu bar, when you right-click the relevant item in the Project Tree, and by pressing Ctrl+P to open the command palette.

Once a project is open, we can generally divide Shoggoth into 3 sections: The menu, the Project Tree and the editing area.

To edit anything in Shoggoth, select it in the Project Tree. There are a few pseudo elements in there to make navigation easier, but the project iself, the encounter sets, the cards, even some of the pseudo elements, can all be opened and edited. Most editor views will also feature ways to add additional sub elements - so a Project view has a button for adding Encounter Sets, Encounter sets can add Cards.

## Creating a Project
To start your creation, first you must create a Project. A Project is a json file. This makes it very easy to share your project with others, or edit stuff across cards that Shoggoth might not support directly.

## Creating player cards


## Creating scenario cards