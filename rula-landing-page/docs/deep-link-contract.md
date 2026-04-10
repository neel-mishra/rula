# Deep-link contract: landing → Streamlit

Base: `NEXT_PUBLIC_STREAMLIT_BASE_URL` (no trailing slash).

| Param  | Values                    | Effect                                      |
|--------|---------------------------|---------------------------------------------|
| `role` | `admin`, `user`, `viewer` | Initial sidebar role (non-prod; see RBAC). |
| `page` | `prospecting`, `map`      | Initial Navigate page.                      |

Examples: `?role=user&page=prospecting`, `?role=admin&page=map`.
