const API = (process.env.REACT_APP_DASHBOARD_API_URL || 'http://127.0.0.1:5001').replace(/\/$/, '');

export async function dashboardRequest(path, {method = 'GET', body, signal} = {}) {
    let response;
    try {
        response = await fetch(`${API}${path}`, {
            method, signal,
            headers: body === undefined ? {} : {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    } catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new Error('The dashboard service is unreachable. Check the backend connection and retry.');
    }
    const data = await response.json();
    const requestId = response.headers.get('X-Request-ID');
    if (!response.ok) {
        const error = new Error(`${data.error || 'Request failed'}${requestId ? ` (request ${requestId})` : ''}`);
        error.status = response.status;
        throw error;
    }
    return data;
}

export const mutation = session => ({revision: session.revision, mutation_id: crypto.randomUUID()});

export async function downloadPlayLog(sessionId, format) {
    const response = await fetch(`${API}/api/sessions/${sessionId}/export?format=${format}`);
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Export failed');
    }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `digitaloc-${sessionId}.${format}`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
