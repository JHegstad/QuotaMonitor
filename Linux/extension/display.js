// Pure display helpers; the worker owns RPC parsing and persistence.
export function remainingValues(quota) {
    return [quota.fiveHourRemaining, quota.weeklyRemaining]
        .filter(value => typeof value === 'number' && Number.isFinite(value))
        .map(value => Math.max(0, Math.min(100, value)));
}

export function limitingLabel(quota) {
    const values = remainingValues(quota);
    return values.length ? `Work ${Math.min(...values)}%` : 'Work --';
}

export function status(remaining) {
    if (typeof remaining !== 'number' || !Number.isFinite(remaining))
        return 'unknown';
    if (remaining >= 50)
        return 'green';
    return remaining >= 20 ? 'yellow' : 'red';
}

function timestamp(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds))
        return null;
    const date = new Date(seconds * 1000);
    return Number.isNaN(date.getTime()) ? null : date;
}

function localDate(date, now) {
    const today = date.getFullYear() === now.getFullYear() &&
        date.getMonth() === now.getMonth() && date.getDate() === now.getDate();
    const options = {hour: '2-digit', minute: '2-digit'};
    if (!today)
        Object.assign(options, {weekday: 'short', day: 'numeric', month: 'short'});
    return date.toLocaleString(undefined, options);
}

export function resetDescription(seconds, now = new Date()) {
    const date = timestamp(seconds);
    if (!date)
        return 'Reset: Ikke registrert';
    const minutes = Math.max(0, Math.floor((date - now) / 60000));
    let countdown;
    if (date <= now) {
        countdown = 'passert – oppdater status';
    } else if (minutes === 0) {
        countdown = '<1m';
    } else {
        const days = Math.floor(minutes / 1440);
        const hours = Math.floor(minutes % 1440 / 60);
        countdown = `${days ? `${days}d ` : ''}${hours}t ${minutes % 60}m`;
    }
    return `Reset: ${localDate(date, now)} (${countdown})`;
}

export function lastUpdatedDescription(seconds, now = new Date()) {
    const date = timestamp(seconds);
    return date ? `Sist oppdatert ${localDate(date, now)}` : 'Sist oppdatert: aldri';
}
