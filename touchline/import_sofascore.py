#!/usr/bin/env python3
"""Import observed official Sofascore page fields without changing roster identity.

Input is a local capture of rendered player pages, not estimated or scraped
position averages. Raw names and page excerpts remain in the ignored .local/.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse

OUTFIELD = ('ATT', 'DEF', 'CRE', 'TEC', 'TAC')
GOALKEEPER = ('SAV', 'ANT', 'TAC', 'BAL', 'AER')
ROOT = Path(__file__).resolve().parent


def normalize_name(value):
    value = value.translate(str.maketrans({'ø': 'o', 'Ø': 'O', 'ł': 'l', 'Ł': 'L',
                                         'ı': 'i', 'đ': 'dj', 'Đ': 'Dj', 'ß': 'ss'}))
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode()
    return re.sub('[^a-z0-9]', '', value.lower())


def parse_observation(row):
    general = row.get('general', row.get('text', ''))
    radar = row.get('radar', row.get('text', ''))
    url = urlparse(row['url'])
    match = re.fullmatch(r'/football/player/[^/]+/(\d+)', url.path)
    if url.scheme != 'https' or url.hostname != 'www.sofascore.com' or not match:
        raise ValueError('Expected an official Sofascore player page URL')
    source_id = int(match[1])
    visible_id = re.search(r'Sofascore Player ID:\s*(\d+)', general)
    if not visible_id or int(visible_id[1]) != source_id:
        raise ValueError('Page was not loaded or visible player ID disagrees with URL')
    birth = re.search(r'\b(\d{1,2})\s+([A-Z]{3,4})\s+(\d{4})\b', general)
    dob = None
    if birth:
        dob = dt.datetime.strptime(f'{birth[1]} {birth[2][:3]} {birth[3]}', '%d %b %Y').date().isoformat()
    def number(label, unit):
        found = re.search(r'\b' + label + r'\s+(\d+(?:\.\d+)?)\s*' + unit + r'\b', general)
        return float(found[1]) if found else None
    height, weight = number('HEIGHT', 'cm'), number('WEIGHT', 'kg')
    if height is not None and not 100 <= height <= 250:
        raise ValueError('Height is outside the supported human range')
    if weight is not None and not 30 <= weight <= 200:
        raise ValueError('Weight is outside the supported human range')
    foot = re.search(r'PREFERRED FOOT\s+(Right|Left|Both)\b', general, re.I)
    position = re.search(r'\bPOSITION\s+([GDMF])\b', general)
    scores = {}
    for key, value in re.findall(r'\b(ATT|DEF|CRE|TEC|TAC|SAV|ANT|BAL|AER)\s+(\d+(?:\.\d+)?)\b', radar):
        score = float(value)
        if key in scores or not 0 <= score <= 100:
            raise ValueError('Duplicate/invalid radar value; do not import averages or mixed periods')
        scores[key] = int(score) if score.is_integer() else score
    if {'ATT', 'SAV'} <= scores.keys():
        raise ValueError('Mixed goalkeeper and outfield radar')
    goalkeeper = position is not None and position[1] == 'G'
    if scores and (('SAV' in scores) != goalkeeper):
        raise ValueError('Radar type does not agree with source position')
    keys = GOALKEEPER if goalkeeper else OUTFIELD
    if set(scores) - set(keys):
        raise ValueError('Radar includes attributes for the wrong player type')
    values = {key: scores.get(key) for key in keys}
    collected_at = row['fetched_at']
    timestamp = dt.datetime.fromisoformat(collected_at.replace('Z', '+00:00'))
    if timestamp.utcoffset() != dt.timedelta(0):
        raise ValueError('Observation timestamp must include the UTC timezone')
    shirt = re.search(r'SHIRT NUMBER\s+(\d+)\b', general)
    nationality = re.search(r'NATIONALITY\s+([A-Z]{3})\b', general)
    return {
        'schema_version': 'sofascore-profile-1',
        'status': 'complete' if all(v is not None for v in values.values()) and height and foot else 'partial',
        'source_player_id': source_id,
        'source_url': row['url'],
        'collected_at_utc': collected_at,
        'source_date_of_birth': dob,
        'source_position': position[1] if position else None,
        'source_nationality': nationality[1] if nationality else None,
        'source_shirt_number': int(shirt[1]) if shirt else None,
        'height_cm': int(height) if height is not None and height.is_integer() else height,
        'weight_kg': weight,
        'preferred_foot': foot[1].lower() if foot else None,
        'attribute_kind': 'goalkeeper' if goalkeeper else 'outfield',
        'attributes': values,
        'attribute_period': 'latest_visible_on_source_page',
        'missing_fields': [k for k, v in values.items() if v is None]
                          + (['height_cm'] if height is None else [])
                          + (['preferred_foot'] if foot is None else [])
                          + (['weight_kg'] if weight is None else []),
        'evidence_sha256': hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    }


def verify_identity(original, row, profile):
    # Never use the old api_player_id as a Sofascore identifier.
    observed_name = row.get('title', '').split(' stats')[0]
    exact = normalize_name(observed_name) == normalize_name(original['name'])
    dob = original.get('date_of_birth')
    observed_dob = profile['source_date_of_birth']
    review = row.get('identity_review', {})
    if (exact and review.get('local_player_id') == original['player_id']
            and review.get('source_player_id') == profile['source_player_id']
            and review.get('evidence') and row.get('review_page_text')):
        return 'reviewed_name_and_club_history'
    if dob and observed_dob != dob:
        raise ValueError('Source birthday does not match the original roster')
    same_team_number = (row.get('roster_club') == original['player_id'].split('-')[0]
                        and row.get('roster_shirt') == original['shirt_number'])
    if exact and (dob or same_team_number):
        return 'name_and_birth_date' if dob else 'name_club_and_shirt_number'
    if row.get('alias_reviewed') and dob and same_team_number:
        return 'reviewed_alias_birth_date_club_and_shirt_number'
    raise ValueError('Identity is ambiguous; manual review required')


def roster_profile(original, row, profile):
    """Keep source identity in .local, and only non-name attributes in the roster."""
    result = {k: v for k, v in profile.items() if k not in ('source_player_id', 'source_url')}
    result['source'] = 'Sofascore'
    conflicts = {}
    for local_key, source_key in (('date_of_birth', 'source_date_of_birth'),
                                  ('shirt_number', 'source_shirt_number')):
        old, new = original.get(local_key), profile.get(source_key)
        if old is not None and new is not None and old != new:
            conflicts[local_key] = {'roster': old, 'source': new}
    # Broad D/M/F categories can differ from a player's specific position.
    # A goalkeeper/outfield disagreement matters when consuming a radar.
    if profile['source_position'] and ((original['position'] == 'GK') !=
                                       (profile['source_position'] == 'G')):
        conflicts['position'] = {'roster': original['position'], 'source': profile['source_position']}
    result['source_conflicts'] = conflicts
    return result


def import_profiles(squads, identity_roster, capture):
    originals = {p['player_id']: p for t in identity_roster['teams'] for p in t['players']}
    rows = {}
    for row in capture['players']:
        pid = row['local_player_id']
        # Later observations replace earlier attempts at the same page.
        rows[pid] = row
    failures = {}
    coverage = Counter()
    for team in squads['teams']:
        for player in team['players']:
            pid = player['player_id']
            row = rows.get(pid)
            if row is None:
                if 'sofascore' not in player:
                    player['sofascore'] = {'schema_version': 'sofascore-profile-1', 'status': 'unmatched'}
                failures[pid] = 'No verified official player page captured'
                coverage[player['sofascore']['status']] += 1
                continue
            try:
                profile = parse_observation(row)
                profile['identity_match'] = verify_identity(originals[pid], row, profile)
                profile = roster_profile(originals[pid], row, profile)
            except (ValueError, KeyError) as error:
                failures[pid] = str(error)
                if 'sofascore' not in player:
                    player['sofascore'] = {'schema_version': 'sofascore-profile-1', 'status': 'needs_review'}
                coverage[player['sofascore']['status']] += 1
                continue
            # A failed/empty refresh must not erase previously obtained scores.
            old = player.get('sofascore', {})
            loses_fields = any(old.get(k) is not None and profile.get(k) is None
                               for k in ('height_cm', 'weight_kg', 'preferred_foot'))
            loses_scores = any(v is not None and profile.get('attributes', {}).get(k) is None
                               for k, v in old.get('attributes', {}).items())
            if loses_fields or loses_scores:
                failures[pid] = 'Incomplete refresh retained the previous profile'
            else:
                player['sofascore'] = profile
            coverage[player['sofascore']['status']] += 1
    profiles = {p['player_id']: p['sofascore'] for t in squads['teams'] for p in t['players']}
    fields = Counter()
    radar_kinds = Counter()
    for p in profiles.values():
        for field in ('height_cm', 'weight_kg', 'preferred_foot'):
            fields[field] += p.get(field) is not None
        if p.get('attributes') and all(v is not None for v in p['attributes'].values()):
            radar_kinds[p['attribute_kind']] += 1
    return {'schema_version': '1', 'players': sum(coverage.values()), 'coverage': dict(coverage),
            'field_coverage': dict(fields), 'complete_radars': dict(radar_kinds),
            'missing_fields': {pid: p['missing_fields'] for pid, p in profiles.items() if p.get('missing_fields')},
            'source_conflicts': {pid: p['source_conflicts'] for pid, p in profiles.items() if p.get('source_conflicts')},
            'failures': failures, 'notes': [
                'Only observed official page values are imported; missing values are never imputed.',
                'Goalkeeper and outfield radars have different meanings and are not interchangeable.',
                'Complete means all five applicable radar scores, height and preferred foot are present; weight is optional.',
                'Sofascore scores are descriptive indices, not calibrated action-success probabilities.',
                'Existing names, IDs and roster attributes are preserved. Source names, URLs and IDs stay in ignored .local captures.',
                'Profiles are a collection-time snapshot, not historical pre-match features; do not use them in historical evaluation without an as-of cutoff.',
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=ROOT/'.local/sofascore/browser-observations.json')
    parser.add_argument('--identities', type=Path, default=ROOT/'.local/sofascore/identity-roster.json')
    parser.add_argument('--squads', type=Path, default=ROOT/'data/league/squads.json')
    parser.add_argument('--report', type=Path, default=ROOT/'artifacts/sofascore-coverage.json')
    args = parser.parse_args()
    squads = json.loads(args.squads.read_text())
    report = import_profiles(squads, json.loads(args.identities.read_text()), json.loads(args.capture.read_text()))
    args.squads.write_text(json.dumps(squads, ensure_ascii=False, indent=2)+'\n')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
