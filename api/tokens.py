"""In-memory session token store for patient/doctor authentication."""
import secrets

# token -> { patient_id, patient_name, role }
_tokens: dict[str, dict] = {}


def create_token(fhir_id: str, name: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    _tokens[token] = {"fhir_id": fhir_id, "name": name, "role": role}
    return token


def resolve_token(token: str) -> dict | None:
    return _tokens.get(token)


def revoke_token(token: str) -> None:
    _tokens.pop(token, None)
