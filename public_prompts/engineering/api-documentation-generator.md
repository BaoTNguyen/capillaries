---
Notes: Part of the public showcase collection
Original Link: ''
Summary: This prompt serves developers creating comprehensive documentation for specific
  API endpoints. The model must produce detailed specs including authentication, request/response
  schemas, error codes, rate limits, and code examples in a specified language.
complexity_level: 2
domain:
- technical
intent:
- build
- communicate
primary_stage: execute
source: public
task_type:
- generate
---

Generate comprehensive API documentation for the **{{api_name}}** API endpoint(s).

Endpoint details:
- Base URL: {{base_url}}
- Endpoint(s): {{endpoint_paths}}
- HTTP method(s): {{http_methods}}
- Authentication: {{auth_method}}
- Request payload or parameters: {{request_schema}}
- Response payload: {{response_schema}}
- Error codes: {{error_codes}}

For each endpoint, generate:
1. **Overview** — 1-2 sentence description of what the endpoint does and when to use it
2. **Authentication** — How to authenticate (header format, token type, scopes required)
3. **Request** — Full specification:
   - URL with path parameters highlighted
   - Query parameters table: name, type, required/optional, description, default value
   - Request body schema with field descriptions and constraints
   - Example request (cURL and {{language}} SDK)
4. **Response** — Full specification:
   - Success response (200/201) with full JSON example
   - Field descriptions table: name, type, description
   - Pagination details if applicable
5. **Error Responses** — Table of possible errors: HTTP code, error code, message, and how to fix
6. **Rate Limits** — Requests per minute/hour, how limits are communicated in headers
7. **Code Examples** — Working examples in {{language}} showing a complete request-response cycle

Output in a developer-friendly format that could be added to a docs site.