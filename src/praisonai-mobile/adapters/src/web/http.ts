/**
 * HttpPort over the browser's fetch.
 *
 * `sendsFromNative` is false, and that is load-bearing rather than
 * informational: on a real device the composition root refuses to hand a
 * hardware-backed secret to an engine whose transport is not native, because
 * a key reaching window.fetch is a key in the JS heap and subject to the
 * webview's CORS policy.
 *
 * In a desktop browser that check is moot -- there is no keychain to protect --
 * but the flag must still be honest or the check is decorative.
 */
import type { HttpPort, HttpRequest, HttpResponse } from "../../../core/src/ports/http.ts";

export function createWebHttp(fetchImpl: typeof fetch = fetch): HttpPort {
  return {
    sendsFromNative: false,

    async send(request: HttpRequest): Promise<HttpResponse> {
      const response = await fetchImpl(request.url, {
        method: request.method,
        headers: request.headers,
        ...(request.body === undefined ? {} : { body: request.body }),
        signal: request.signal,
      });

      const headers: Record<string, string> = {};
      response.headers.forEach((value, key) => {
        headers[key] = value;
      });

      return { status: response.status, headers, body: response.body };
    },
  };
}
