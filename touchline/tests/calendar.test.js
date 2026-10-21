import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { januarySchedule, calendarDays } from '../calendar.js';
const source = JSON.parse(readFileSync(new URL('../data/league/league.json', import.meta.url)));
const league = januarySchedule(source);

test('All forty fixtures occur once, split equally across January weekends', () => {
  const days = calendarDays(league, 3);
  assert.equal(days.month.length, 31);
  assert.equal(days.month[0].date, '2027-01-01');
  assert.equal(days.month[30].date, '2027-01-31');
  const matches = days.month.flatMap(day => day.matches);
  assert.equal(matches.length, 40);
  assert.equal(new Set(matches.map(match => match.match_id)).size, 40);
  for (const day of days.month) {
    if (day.matches.length) {
      assert.ok(day.weekday >= 5);
      assert.equal(day.matches.length, 5);
    } else assert.deepEqual(day.matches, []);
  }
  assert.equal(source.weeks[0].date, '2026-10-24');
});

test('Current week has seven days and no future scores or results', () => {
  const { week, month } = calendarDays(league, 3);
  assert.equal(week.length, 7);
  assert.equal(week[0].date, '2027-01-11');
  assert.equal(week[6].date, '2027-01-17');
  assert.ok(week.every(day => day.currentWeek));
  assert.ok(week.slice(0, 5).every(day => !day.matches.length));
  for (const match of month.flatMap(day => day.matches)) {
    assert.equal(Boolean(match.score), match.matchweek < 3);
    assert.equal(match.goals, undefined);
    assert.equal(match.status, undefined);
  }
});

test('Club scope retains empty days and only the club’s fixtures', () => {
  for (const club of league.teams) {
    const { month, week } = calendarDays(league, 3, club.club_id);
    assert.equal(month.length, 31);
    assert.equal(month.flatMap(day => day.matches).length, 4);
    assert.equal(week.flatMap(day => day.matches).length, 1);
    assert.ok(month.flatMap(day => day.matches).every(match => [match.home_name, match.away_name].includes(club.name)));
  }
});
