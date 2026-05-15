/**
 * Centralized fetch wrapper that automatically injects the CSRF token.
 *
 * Reads the token from <meta name="csrf-token"> (set in base.html).
 * Use csrfFetch() as a drop-in replacement for fetch() on POST/PUT/DELETE.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
function csrfFetch(url, options) {
  "use strict";
  options = options || {};
  var meta = document.querySelector("meta[name=csrf-token]");
  var token = meta ? meta.content : "";
  var headers = options.headers || {};
  if (!(headers instanceof Headers)) {
    headers = Object.assign({ "X-CSRFToken": token }, headers);
  }
  options.headers = headers;
  return fetch(url, options);
}
