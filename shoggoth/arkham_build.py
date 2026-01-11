import datetime
datetime.datetime.now().isoformat()

def do(project):
	data = {
		"meta": {
			"author": project.data['author'],
			"code": project.id,
			"language": "en",
			"name": project.name,

			"description": project.data['description'],
			"date_updated": datetime.date.today().isoformat(),
			"banner_url": project.get('banner_url'),
			"banner_credit": project.get('banner_url'),

			"external_link": project.get('website_url'),
			"generator": "Shoggoth 0.0.24",
			"status": project.get('status', 'draft'),  # "draft" | "alpha" | "beta" | "complete" | "final"
			"tags": "",
			"types": ["campaign", "player_cards", "investigators", "rework", "scenario"],
			"url": project.get('hosting_url')
		},
		"data": {
			"cards": [],
			"encounter_sets": []
		}
	}
	for encounter_set in project.encounter_sets:
		data["encounter_sets"].append({
			"code": encounter_set.code,
			"name": encounter_set.name,
			"icon_url": encounter_set.get('icon_url')
		})
	for card in project.cards:
		data["cards"].append({
			"back_flavor": "",
			"back_illustrator": "",
			"back_link": "",
			"back_name": "",
			"back_text": "",
			"back_traits": "",
			"bonded_to": "",
			"clues_fixed": "",
			"clues": "",
			"code": "",
			"cost": "",
			"customization_change": "",
			"customization_options": "",
			"customization_text": "",
			"deck_limit": "",
			"deck_options": "",
			"deck_requirements": "",
			"doom": "",
			"double_sided": False,
			"encounter_code": "",
			"encounter_position": card.encounter_number,
			"enemy_damage": "",
			"enemy_evade": "",
			"enemy_fight": "",
			"enemy_horror": "",
			"errata_date": "",
			"exceptional": "",
			"exile": "",
			"faction_code": "",
			"faction2_code": "",
			"faction3_code": "",
			"flavor": "",
			"health_per_investigator": "",
			"health": "",
			"hidden": "",
			"illustrator": "",
			"is_unique": "",
			"myriad": "",
			"name": "",
			"pack_code": "",
			"permanent": "",
			"position": "",
			"quantity": "",
			"restrictions": "",
			"sanity": "",
			"shroud": "",
			"side_deck_options": "",
			"side_deck_requirements": "",
			"skill_agility": "",
			"skill_combat": "",
			"skill_intellect": "",
			"skill_wild": "",
			"skill_willpower": "",
			"slot": "",
			"stage": "",
			"subname": "",
			"subtype_code": "",
			"tags": "",
			"text": "",
			"traits": "",
			"type_code": "",
			"vengeance": "",
			"victory": "",
			"xp": "",
			"attachments": "",
			"back_image_url": "",
			"back_thumbnail_url": "",
			"card_pool_extension": "",
			"image_url": "",
			"thumbnail_url": "",
		})
