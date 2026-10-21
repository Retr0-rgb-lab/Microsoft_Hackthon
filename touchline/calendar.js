// Simulation dates use the January within the dataset's season, in UK local time.
const DAY = 86400000;
const dateKey = date => date.toISOString().slice(0, 10);
export function januarySchedule(league) {
  const year = Number(league.competition.season.slice(0, 4)) + 1;
  const first = new Date(Date.UTC(year, 0, 1));
  const saturday = 1 + (6 - first.getUTCDay() + 7) % 7;
  return { ...league, calendarYear: year, weeks: league.weeks.map((week, index) => {
    const start = new Date(Date.UTC(year, 0, saturday + index * 7));
    return { ...week, date: dateKey(start), matches: week.matches.map((match, i) => {
      const date = new Date(+start + (i < Math.ceil(week.matches.length / 2) ? 0 : DAY));
      return { ...match, kickoff_local: `${dateKey(date)}T${match.kickoff_local.slice(11)}` };
    }) };
  }) };
}
export function calendarDays(league, currentWeek, clubId = null) {
  const anchor = league.weeks.find(week => week.week === currentWeek)?.date;
  const start = new Date(`${anchor || `${league.calendarYear}-01-01`}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
  const matches = league.weeks.flatMap(week => week.matches).filter(match => !clubId ||
    [match.home_club_id, match.away_club_id].includes(clubId));
  const makeDay = date => ({ date: dateKey(date), weekday: (date.getUTCDay() + 6) % 7,
    currentWeek: +date >= +start && +date < +start + 7 * DAY,
    matches: matches.filter(match => match.kickoff_local.slice(0, 10) === dateKey(date)).map(match => ({
      match_id: match.match_id, matchweek: match.matchweek, home_name: match.home_name,
      away_name: match.away_name, kickoff_local: match.kickoff_local, venue: match.venue,
      ...(match.matchweek < currentWeek && match.status === 'finished' ? { score: match.score } : {}),
    })).sort((a, b) => a.kickoff_local.localeCompare(b.kickoff_local)) });
  return { month: Array.from({ length: 31 }, (_, i) => makeDay(new Date(Date.UTC(league.calendarYear, 0, i + 1)))),
    week: Array.from({ length: 7 }, (_, i) => makeDay(new Date(+start + i * DAY))) };
}
