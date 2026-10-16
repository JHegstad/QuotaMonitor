// Runs in GJS (-m) or JavaScriptCore (-m), without a GNOME session.
import {lastUpdatedDescription, limitingLabel, resetDescription, status} from '../extension/display.js';

function assert(value, message) {
    if (!value)
        throw new Error(message);
}

assert(limitingLabel({fiveHourRemaining: 74, weeklyRemaining: 41}) === 'Work 41%', 'weekly limits');
assert(limitingLabel({fiveHourRemaining: 18, weeklyRemaining: 63}) === 'Work 18%', 'five-hour limits');
assert(limitingLabel({fiveHourRemaining: 0, weeklyRemaining: null}) === 'Work 0%', 'zero is real data');
assert(limitingLabel({weeklyRemaining: 61}) === 'Work 61%', 'one window');
assert(limitingLabel({}) === 'Work --', 'no windows');
assert(limitingLabel({fiveHourRemaining: NaN, weeklyRemaining: null}) === 'Work --', 'invalid windows');
for (const [remaining, expected] of [[100, 'green'], [50, 'green'], [49, 'yellow'], [20, 'yellow'],
    [19, 'red'], [0, 'red'], [null, 'unknown'], [undefined, 'unknown']]) {
    assert(status(remaining) === expected, `threshold ${remaining}`);
}

const now = new Date(2026, 9, 16, 8, 0, 0);
const sameDay = new Date(2026, 9, 16, 12, 12, 0);
assert(resetDescription(sameDay / 1000, now).endsWith('(4t 12m)'), 'same-day countdown');
const nextWeek = new Date(now.getTime() + (6 * 1440 + 85) * 60000);
assert(resetDescription(nextWeek / 1000, now).endsWith('(6d 1t 25m)'), 'week countdown');
assert(resetDescription(nextWeek / 1000, now).length > resetDescription(sameDay / 1000, now).length,
    'other-day reset includes a date');
assert(resetDescription(null, now) === 'Reset: Ikke registrert', 'missing reset');
assert(resetDescription(now / 1000 - 1, now).includes('passert'), 'past reset is not rolled forward');
assert(resetDescription(now / 1000 + 30, now).endsWith('(<1m)'), 'less than a minute');
assert(lastUpdatedDescription(null, now) === 'Sist oppdatert: aldri', 'never updated');
assert(lastUpdatedDescription(now / 1000, now).startsWith('Sist oppdatert '), 'updated time');
if (typeof print === 'function')
    print('Display checks passed.');
else
    console.log('Display checks passed.');
