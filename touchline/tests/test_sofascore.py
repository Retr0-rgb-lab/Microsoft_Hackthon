"""Official observations must remain attributable, partial and identity-safe."""
import copy
import json
from pathlib import Path
import unittest

from generate import CLUBS, Match, build_metadata, load_squads, select_lineup
from import_sofascore import (GOALKEEPER, OUTFIELD, import_profiles,
                             parse_observation, verify_identity)

ROOT = Path(__file__).resolve().parents[1]


def observation(goalkeeper=False):
    keys = GOALKEEPER if goalkeeper else OUTFIELD
    return {
        'local_player_id': 'ARS-01', 'url': 'https://www.sofascore.com/football/player/example/123',
        'title': 'Example Player stats and ratings | Sofascore',
        'roster_club': 'ARS', 'roster_shirt': 1, 'fetched_at': '2026-10-23T12:00:00Z',
        'general': 'General info\nNATIONALITY\nENG\n15 SEPT 2000\nHEIGHT\n186 cm\n'
                   'PREFERRED FOOT\nLeft\nPOSITION\n' + ('G' if goalkeeper else 'D') +
                   '\nSHIRT NUMBER\n1\nSofascore Player ID:\n123\n',
        'radar': 'Attribute Overview\n' + '\n'.join(f'{key}\n{70+i}' for i, key in enumerate(keys)),
    }


def roster():
    return {'teams': [{'players': [{
        'player_id': 'ARS-01', 'name': 'Example Player', 'shirt_number': 1,
        'date_of_birth': '2000-09-15', 'position': 'DEF', 'api_player_id': 9999,
    }]}]}


class SofascoreImportTests(unittest.TestCase):
    def test_parse_real_units_and_distinct_radars(self):
        for keeper, keys in ((False, OUTFIELD), (True, GOALKEEPER)):
            profile = parse_observation(observation(keeper))
            self.assertEqual(profile['attributes'], {key: 70+i for i, key in enumerate(keys)})
            self.assertEqual(profile['height_cm'], 186)
            self.assertEqual(profile['preferred_foot'], 'left')
            self.assertEqual(profile['source_date_of_birth'], '2000-09-15')
            self.assertIsNone(profile['weight_kg'])
            self.assertEqual(profile['status'], 'complete')

    def test_reject_wrong_page_average_and_wrong_radar(self):
        for change in ({'url': 'https://www.sofascore.com/football/player/example/456'},
                       {'general': ''}, {'radar': 'ATT\n72\nATT\n50'},
                       {'radar': 'DEF\n101'}, {'radar': 'ANT\n40\nATT\n50'},
                       {'fetched_at': '2026-10-23T12:00:00'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_observation({**observation(), **change})

    def test_birth_mismatch_requires_explicit_identity_review(self):
        original = roster()['teams'][0]['players'][0]
        row = observation()
        original['date_of_birth'] = '2000-09-14'
        with self.assertRaises(ValueError):
            verify_identity(original, row, parse_observation(row))
        row['identity_review'] = {'local_player_id': 'ARS-01', 'source_player_id': 123,
                                  'evidence': 'Name, club, nationality and shirt checked.'}
        row['review_page_text'] = 'Example Player\nExample Club\n' + row['general']
        self.assertEqual(verify_identity(original, row, parse_observation(row)),
                         'reviewed_name_and_club_history')
        row['identity_review']['source_player_id'] = 456
        with self.assertRaises(ValueError):
            verify_identity(original, row, parse_observation(row))

    def test_additive_idempotent_import_and_failed_refresh(self):
        identities = roster()
        squads = copy.deepcopy(identities)
        player = squads['teams'][0]['players'][0]
        player['name'] = 'Aster Player 01'
        before = copy.deepcopy(player)
        capture = {'players': [observation()]}
        report = import_profiles(squads, identities, capture)
        self.assertFalse(report['failures'])
        self.assertEqual({k: v for k, v in player.items() if k != 'sofascore'}, before)
        self.assertNotIn('source_url', player['sofascore'])
        self.assertNotIn('source_player_id', player['sofascore'])
        imported = copy.deepcopy(squads)
        import_profiles(squads, identities, capture)
        self.assertEqual(squads, imported)
        capture['players'][0]['radar'] = ''
        report = import_profiles(squads, identities, capture)
        self.assertIn('ARS-01', report['failures'])
        self.assertEqual(squads, imported)

    def test_missing_values_are_null_and_unmatched_are_explicit(self):
        identities = roster()
        squads = copy.deepcopy(identities)
        import_profiles(squads, identities, {'players': [{**observation(), 'radar': ''}]})
        profile = squads['teams'][0]['players'][0]['sofascore']
        self.assertEqual(profile['status'], 'partial')
        self.assertTrue(all(v is None for v in profile['attributes'].values()))
        unmatched = copy.deepcopy(identities)
        import_profiles(unmatched, identities, {'players': []})
        self.assertEqual(unmatched['teams'][0]['players'][0]['sofascore']['status'], 'unmatched')

    def test_checked_in_coverage_and_ranges(self):
        players = [p for t in load_squads().values() for p in t['players']]
        report = json.loads((ROOT/'artifacts/sofascore-coverage.json').read_text())
        self.assertEqual(len(players), 566)
        self.assertEqual(report['players'], len(players))
        self.assertFalse(report['failures'])
        for player in players:
            profile = player['sofascore']
            keys = GOALKEEPER if profile['attribute_kind'] == 'goalkeeper' else OUTFIELD
            self.assertEqual(set(profile['attributes']), set(keys))
            self.assertTrue(all(v is None or 0 <= v <= 100 for v in profile['attributes'].values()))
            self.assertNotIn('source_url', profile)
        for field, count in report['field_coverage'].items():
            self.assertEqual(count, sum(p['sofascore'][field] is not None for p in players))


class SofascoreGeneratorTests(unittest.TestCase):
    def test_starters_bench_and_substitution_keep_their_own_profiles(self):
        squads = load_squads()
        lineups = [select_lineup(c['club_id'], squads) for c in CLUBS[:2]]
        sim = Match(73, home=CLUBS[0], away=CLUBS[1], lineups=lineups)
        source = {p['player_id']: p for lineup in lineups for p in lineup}
        for p in sim.player_by_id.values():
            self.assertEqual(p['sofascore'], source[p['real_player_id']]['sofascore'])
        metadata = build_metadata(sim)
        self.assertEqual(len(metadata['players']), 28)
        self.assertTrue(all(p.get('sofascore') for p in metadata['players']))
        incoming = copy.deepcopy(sim.player_by_id['H12']['sofascore'])
        sim.administrative_events = [(0, 'substitution', 5, 12)]
        sim.apply_administrative_events()
        self.assertEqual(sim.players[5]['id'], 'H12')
        self.assertEqual(sim.players[5]['sofascore'], incoming)
        # Independent objects: mutations cannot change the squad or frozen metadata.
        sim.players[5]['sofascore']['height_cm'] = 123
        self.assertEqual(sim.player_by_id['H12']['sofascore'], incoming)
        self.assertEqual(next(p for p in metadata['players'] if p['player_id']=='H12')['sofascore'], incoming)

    def test_disabling_style_keeps_the_neutral_policy_reproducible(self):
        squads = load_squads()
        lineups = [select_lineup(c['club_id'], squads) for c in CLUBS[:2]]
        without = copy.deepcopy(lineups)
        for lineup in without:
            for player in lineup:
                player.pop('sofascore', None)
        sims = [Match(73, home=CLUBS[0], away=CLUBS[1], lineups=x,
                      attribute_strength=0.0) for x in (lineups, without)]
        for frame in range(1, 501):
            for sim in sims:
                sim.step(frame)
        self.assertEqual(sims[0].events, sims[1].events)
        self.assertEqual(sims[0].tracking(500), sims[1].tracking(500))
        self.assertEqual(sims[0].decisions, sims[1].decisions)


if __name__ == '__main__':
    unittest.main()
