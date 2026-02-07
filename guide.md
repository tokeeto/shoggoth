# Shoggoth

## Installation
To install shoggoth, you got 2 options:
The easy option is to download the latest release from (https://github.com/tokeeto/shoggoth/releases/latest/), unpack it, and run it.
Shoggoth may prompt a warning on both Mac and Windows, as I've not paid for a certificate for the software.
The slightly more technical option, is to install Shoggoth as a python package. `python -m pip install shoggoth` or `uvx shoggoth`. It's available as a tool on pypi, so use whatever method you prefer.

## Why Shoggoth?

The short answer: Speed, customization, and file format.

I took over maintainance of the Strange Eons AHLCG plugin some time ago. And rather quickly I discovered the shortcomings of SE. SE is a general game component creator, that was proficiently coerced into creating AH cards. But it does not "know" about AH cards. Neither does it support pdf creation - just images.

Shoggoth is built from the ground up to support all manner of custom AH content. And it's faster, and takes advantage of threading and multiple cores. It allows you to create custom content very easily, and to make whatever cards you want - want a card that's the Player back on one side and Encounter back on the other? Sure thing. You want an asset on one side and an enemy on the other? Not even hard. Encounter sets are integrated parts of the data model. You just set the icon for the encounter set, and all cards are instantly updated.
We even have a top-down graph editor for locations for easy visual inspection to see if your map is created correctly.

By now, we, the AH community has several options for creating cards. You should pick Shoggoth if you like it obviously, if you want to create very custom cards, want to create better campaign guides or want to support a python open source project.

When should you _not_ pick Shoggoth then? If you're already familiar with one of the other tools, and they do everything you need, then there's really no reason to swap.
If you only want to create cards confirming to known standards and variations, then there's propably nothing exciting for you in Shoggoth that the other editors can't also do.

## Projects
In Shoggoth, a file is a project - roughly analogous to an expansion. A project can contain encounter sets, campaign cards, player cards, and guides (rule books, if you will).
A single project is meant to contain a single campaign.
To make it easier to quickly prototype new ideas, Shoggoth supports having multiple projects open at once, so you can create all your silly ideas in your "scratchpad-project" and then create proper content in your "real" project.

### Campaigns
Campaigns are divided into encounter sets. Each set contains cards. When you create new cards, they're automatically show in the proper set and substructure. An encounter set with only encounter cards, are shown as a simple encounter set. Otherwise you'll get a few more sub groups to split out your cards.

### Player cards
Player cards are automatically split into either their class, or as belonging to an investigator.

### Campaign Guides
Campaign guides are pure html. I'm currently looking into what the final version of the campaign should look like. It will probably be something like small seperate guides for each encounter set, that are then automatically combined in the end.

## Cards
Todo: describe card editor here. (Trust me though, it's easy enough to use)

## The data model
Every project is a json file, and every card is a json object. That means it's very easy to transfer and read projects and cards. No more binary files with embedded images.

## Exporting
Shoggoth supports exporting to images, pdf, arkham.build and TTS.

## Converting existing projects
There's a tool for converting existing SE projects into Shoggoth projects. It requires that you've installed openjdk 11 on your machine, and you then need to point shoggoth towards your installation.
