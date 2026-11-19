// Local JSON stdin/stdout adapter around the unmodified vendored MIT core.
import { readFileSync } from 'node:fs';
import { calculateBazi, toBaziJson, deriveBaziRelations, toBaziRelationsJson } from '../vendor/taibu-core/dist/domains/bazi/index.js';
import { calculateDailyAlmanac, toAlmanacJson } from '../vendor/taibu-core/dist/domains/almanac/index.js';

try {
  const { patron, date, timezone } = JSON.parse(readFileSync(0, 'utf8'));
  let chart;
  let input;
  let status = 'general';
  if (patron.birth_date && patron.gender && patron.birth_timezone) {
    const [year, month, day] = patron.birth_date.split('-').map(Number);
    input = {
      gender: patron.gender, birthYear: year, birthMonth: month, birthDay: day,
      timezone: patron.birth_timezone, dayBoundary: 'midnight', calendarType: 'solar',
    };
    if (patron.birth_hour !== null) {
      input.birthHour = patron.birth_hour;
      input.birthMinute = patron.birth_minute ?? 0;
    }
    if (patron.longitude !== null) input.longitude = patron.longitude;
    chart = calculateBazi(input);
    status = chart.birthTimeUnknown ? 'three_pillars' : 'four_pillars';
  }
  const daily = await calculateDailyAlmanac({ date, timezone, ...(chart ? { dayMaster: chart.dayMaster } : {}) });
  const natal = chart ? Object.entries(chart.fourPillars).map(([label, pillar]) => ({
    label, stem: pillar.stem, branch: pillar.branch,
  })) : [];
  const relations = chart ? toBaziRelationsJson(deriveBaziRelations(chart, { day: date }, input)) : null;
  process.stdout.write(JSON.stringify({
    engine: { name: 'taibu-core', version: '4.1.0', commit: '4b2a51a' },
    personalization: status,
    almanac: toAlmanacJson(daily),
    bazi: chart ? toBaziJson(chart) : null,
    relations,
    coordinates: { day_stem: daily.dayInfo.stem, day_branch: daily.dayInfo.branch,
      day_master: chart?.dayMaster ?? null, natal },
  }));
} catch (error) {
  process.stderr.write(String(error.message));
  process.exitCode = 1;
}
