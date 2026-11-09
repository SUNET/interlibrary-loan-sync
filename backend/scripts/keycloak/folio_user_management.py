"""FOLIO User Management Functions

Functions for creating and managing users in a FOLIO instance
using FolioApiClient for authentication and API communication.

Usage:
    from folio_user_management import FolioUserManager

    from api_client import FolioApiClient

    client = FolioApiClient(username="...", secret="...")
    manager = FolioUserManager(client)

    # List available patron groups
    groups = manager.get_patron_groups()

    # Create a full user with credentials and permissions
    user = manager.create_full_user(
        username="jane.doe",
        password="securePassword123",
        last_name="Doe",
        first_name="Jane",
        patron_group_id="<uuid>",
        permissions=["ui-users.view"],
    )
"""

import logging
import os
import uuid
from typing import Optional

import requests
from dotenv import load_dotenv

from api_client import FolioApiClient

logger = logging.getLogger(__name__)


class FolioUserManagerError(Exception):
    """Raised when a FOLIO user management operation fails."""


class FolioUserManager:
    """Client for managing users in a FOLIO instance via the FolioApiClient."""

    def __init__(self, client: FolioApiClient):
        self.client = client

    def _request(self, method: str, path: str, **kwargs):
        """Make an HTTP request to the FOLIO API via FolioApiClient.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path (e.g. "/users").
            **kwargs: Additional arguments passed to the client method.

        Returns:
            The response object.

        Raises:
            FolioUserManagerError: If the request fails.
        """
        # Strip leading slash since FolioApiClient adds the base URL
        endpoint = path.lstrip("/")

        method_upper = method.upper()
        if method_upper == "GET":
            response = self.client.get(endpoint, **kwargs)
        elif method_upper == "POST":
            json_data = kwargs.pop("json", None)
            response = self.client.post(endpoint, json_data=json_data, **kwargs)
        elif method_upper == "PUT":
            json_data = kwargs.pop("json", None)
            response = self.client.put(endpoint, json_data=json_data, **kwargs)
        elif method_upper == "DELETE":
            response = self.client.delete(endpoint, **kwargs)
        elif method_upper == "PATCH":
            json_data = kwargs.pop("json", None)
            response = self.client.patch(endpoint, json_data=json_data, **kwargs)
        else:
            raise FolioUserManagerError(f"Unsupported HTTP method: {method}")

        if not response.ok:
            raise FolioUserManagerError(
                f"{method} {path} failed ({response.status_code}): {response.text}"
            )
        return response

    # -------------------------------------------------------------------------
    # Patron Groups
    # -------------------------------------------------------------------------

    def get_patron_groups(self, limit: int = 100) -> list[dict]:
        """Fetch all patron groups from the tenant.

        Returns:
            List of patron group objects with 'id', 'group', 'desc' keys.
        """
        resp = self._request("GET", f"/groups?limit={limit}")
        return resp.json().get("usergroups", [])

    def get_patron_group_by_name(self, name: str) -> Optional[dict]:
        """Find a patron group by its name.

        Args:
            name: The patron group name (e.g. "staff", "faculty").

        Returns:
            The patron group dict, or None if not found.
        """
        resp = self._request("GET", f'/groups?query=group=="{name}"')
        groups = resp.json().get("usergroups", [])
        return groups[0] if groups else None

    # -------------------------------------------------------------------------
    # User CRUD (mod-users)
    # -------------------------------------------------------------------------

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """Look up a user by username.

        Args:
            username: The FOLIO username.

        Returns:
            The user dict, or None if not found.
        """
        resp = self._request("GET", f'/users?query=username=="{username}"')
        users = resp.json().get("users", [])
        return users[0] if users else None

    def create_user(
        self,
        username: str,
        last_name: str,
        patron_group_id: Optional[str] = None,
        first_name: str = "",
        email: str = "",
        active: bool = True,
        user_id: Optional[str] = None,
    ) -> dict:
        """Create a new user record in mod-users.

        Args:
            username: Login username.
            last_name: User's last name (required by FOLIO).
            patron_group_id: UUID of the patron group (optional).
            first_name: User's first name.
            email: User's email address.
            active: Whether the user account is active.
            user_id: Specific UUID to assign. Auto-generated if not provided.

        Returns:
            The created user object from FOLIO.
        """
        user_id = user_id or str(uuid.uuid4())

        user_payload: dict = {
            "id": user_id,
            "username": username,
            "active": active,
            "personal": {
                "lastName": last_name,
            },
            "departments": [],
        }

        if patron_group_id:
            user_payload["patronGroup"] = patron_group_id
        if first_name:
            user_payload["personal"]["firstName"] = first_name
        if email:
            user_payload["personal"]["email"] = email

        resp = self._request("POST", "/users", json=user_payload)
        user = resp.json()
        logger.info("Created user %s (id: %s)", username, user["id"])
        return user

    def update_user(self, user: dict) -> dict:
        """Update an existing user record.

        Args:
            user: The full user object with modifications.

        Returns:
            The updated user object.
        """
        user_id = user["id"]
        self._request("PUT", f"/users/{user_id}", json=user)
        logger.info("Updated user %s", user_id)
        return user

    def delete_user(self, user_id: str) -> None:
        """Delete a user record.

        Args:
            user_id: The UUID of the user to delete.
        """
        self._request("DELETE", f"/users/{user_id}")
        logger.info("Deleted user %s", user_id)

    # -------------------------------------------------------------------------
    # Credentials (mod-login)
    # -------------------------------------------------------------------------

    def set_user_credentials(self, user_id: str, password: str) -> None:
        """Set login credentials for a user.

        Args:
            user_id: The UUID of the user.
            password: The password to set.
        """
        payload = {
            "userId": user_id,
            "password": password,
        }
        self._request("POST", "/authn/credentials", json=payload)
        logger.info("Set credentials for user %s", user_id)

    # -------------------------------------------------------------------------
    # Keycloak Realm Role Assignment
    # -------------------------------------------------------------------------

    def _keycloak_headers(self) -> dict:
        """Build headers for Keycloak Admin API requests."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.client.access_token}",
        }

    def _keycloak_admin_url(self, path: str) -> str:
        """Build a Keycloak Admin API URL.

        Args:
            path: Path relative to /admin/realms/{realm}/ (e.g. "roles").
        """
        return (
            f"{self.client.auth_base_url}/admin/realms/{self.client.realm}"
            f"/{path.lstrip('/')}"
        )

    def get_realm_role(self, role_name: str) -> dict:
        """Look up a realm role by name from Keycloak.

        Args:
            role_name: The name of the realm role (e.g. "adminRole").

        Returns:
            The role object containing id, name, containerId, etc.

        Raises:
            FolioUserManagerError: If the role is not found or the request fails.
        """
        url = self._keycloak_admin_url(f"roles/{role_name}")
        response = requests.get(
            url, headers=self._keycloak_headers(), timeout=self.client.timeout
        )
        if not response.ok:
            raise FolioUserManagerError(
                f"Failed to look up realm role '{role_name}' "
                f"({response.status_code}): {response.text}"
            )
        return response.json()

    def assign_realm_role(self, user_id: str, role_name: str = "adminRole") -> None:
        """Assign a realm role to a user via the Keycloak Admin API.

        Looks up the role by name first, then posts the role mapping.

        Args:
            user_id: The UUID of the user (must match the Keycloak user ID).
            role_name: The name of the realm role to assign.

        Raises:
            FolioUserManagerError: If the role lookup or assignment fails.
        """
        # Look up the role to get its id and containerId
        role = self.get_realm_role(role_name)

        url = self._keycloak_admin_url(f"users/{user_id}/role-mappings/realm")
        payload = [role]
        response = requests.post(
            url, json=payload, headers=self._keycloak_headers(),
            timeout=self.client.timeout,
        )
        if not response.ok:
            raise FolioUserManagerError(
                f"Failed to assign role '{role_name}' to user {user_id} "
                f"({response.status_code}): {response.text}"
            )
        logger.info("Assigned role '%s' to user %s", role_name, user_id)

    # -------------------------------------------------------------------------
    # Permissions (mod-permissions)
    # -------------------------------------------------------------------------

    def get_available_permissions(
        self, query: str = "", limit: int = 100
    ) -> list[dict]:
        """List available permissions in the system.

        Args:
            query: Optional CQL query to filter permissions.
            limit: Maximum number of results.

        Returns:
            List of permission objects.
        """
        params = f"limit={limit}"
        if query:
            params += f"&query={query}"
        resp = self._request("GET", f"/perms/permissions?{params}")
        return resp.json().get("permissions", [])

    def get_user_permissions(self, user_id: str) -> Optional[dict]:
        """Get the permissions record for a user.

        Args:
            user_id: The UUID of the user.

        Returns:
            The permissions user object, or None if not found.
        """
        resp = self._request("GET", f'/perms/users?query=userId=="{user_id}"')
        perm_users = resp.json().get("permissionUsers", [])
        return perm_users[0] if perm_users else None

    def assign_permissions(self, user_id: str, permissions: list[str]) -> dict:
        """Create a permissions record for a user with the given permissions.

        Args:
            user_id: The UUID of the user.
            permissions: List of permission names to assign.

        Returns:
            The created permission user object.
        """
        payload = {
            "userId": user_id,
            "permissions": permissions,
        }
        resp = self._request("POST", "/perms/users", json=payload)
        result = resp.json()
        logger.info(
            "Assigned %d permissions to user %s", len(permissions), user_id
        )
        return result

    def add_permission(self, perms_user_id: str, permission: str) -> None:
        """Add a single permission to an existing permissions record.

        Args:
            perms_user_id: The UUID of the permissions user record
                           (not the user UUID).
            permission: The permission name to add.
        """
        payload = {"permissionName": permission}
        self._request(
            "POST",
            f"/perms/users/{perms_user_id}/permissions",
            json=payload,
        )
        logger.info("Added permission %s to perms user %s", permission, perms_user_id)

    # -------------------------------------------------------------------------
    # Service Points (mod-inventory-storage)
    # -------------------------------------------------------------------------

    def get_service_points(self, limit: int = 100) -> list[dict]:
        """Fetch available service points.

        Returns:
            List of service point objects.
        """
        resp = self._request("GET", f"/service-points?limit={limit}")
        return resp.json().get("servicepoints", [])

    def assign_service_points(
        self,
        user_id: str,
        service_point_ids: list[str],
        default_service_point_id: str,
    ) -> dict:
        """Assign service points to a user.

        Args:
            user_id: The UUID of the user.
            service_point_ids: List of service point UUIDs to assign.
            default_service_point_id: UUID of the default service point.

        Returns:
            The created service points user object.
        """
        payload = {
            "userId": user_id,
            "servicePointsIds": service_point_ids,
            "defaultServicePointId": default_service_point_id,
        }
        resp = self._request("POST", "/service-points-users", json=payload)
        result = resp.json()
        logger.info("Assigned %d service points to user %s", len(service_point_ids), user_id)
        return result

    # -------------------------------------------------------------------------
    # Convenience: Full User Creation
    # -------------------------------------------------------------------------

    def create_full_user(
        self,
        username: str,
        password: str,
        last_name: str,
        patron_group_id: Optional[str] = None,
        first_name: str = "",
        email: str = "",
        active: bool = True,
        permissions: Optional[list[str]] = None,
        service_point_ids: Optional[list[str]] = None,
        default_service_point_id: Optional[str] = None,
        admin_role: bool = False,
    ) -> dict:
        """Create a user with credentials, permissions, and service points.

        This is a convenience function that combines all the steps needed
        to create a fully functional FOLIO user:
        1. Create the user record
        2. Set login credentials
        3. Assign permissions (if provided)
        4. Assign service points (if provided)
        5. Assign Keycloak admin role (if requested)

        Args:
            username: Login username.
            password: Login password.
            last_name: User's last name.
            patron_group_id: UUID of the patron group (optional).
            first_name: User's first name.
            email: User's email address.
            active: Whether the user account is active.
            permissions: List of permission names to assign.
            service_point_ids: List of service point UUIDs.
            default_service_point_id: UUID of the default service point.
            admin_role: Whether to assign the Keycloak adminRole.

        Returns:
            The created user object.

        Raises:
            FolioUserManagerError: If any step fails. Note that partial
                creation may have occurred (e.g. user created but
                credentials not set).
        """
        # Step 1: Create user record
        user = self.create_user(
            username=username,
            last_name=last_name,
            patron_group_id=patron_group_id,
            first_name=first_name,
            email=email,
            active=active,
        )
        user_id = user["id"]
        logger.info("Step 1/5: User record created (id: %s)", user_id)

        # Step 2: Set credentials
        self.set_user_credentials(user_id, password)
        logger.info("Step 2/5: Credentials set")

        # Step 3: Assign permissions
        if permissions:
            self.assign_permissions(user_id, permissions)
            logger.info("Step 3/5: %d permissions assigned", len(permissions))
        else:
            logger.info("Step 3/5: No permissions to assign (skipped)")

        # Step 4: Assign service points
        if service_point_ids and default_service_point_id:
            self.assign_service_points(
                user_id, service_point_ids, default_service_point_id
            )
            logger.info("Step 4/5: Service points assigned")
        else:
            logger.info("Step 4/5: No service points to assign (skipped)")

        # Step 5: Assign Keycloak admin role
        if admin_role:
            self.assign_realm_role(user_id, role_name="adminRole")
            logger.info("Step 5/5: Admin role assigned")
        else:
            logger.info("Step 5/5: No admin role to assign (skipped)")

        return user


if __name__ == "__main__":
    load_dotenv()
    prefix = "HORIZON"
    tenant_env = os.getenv(f"TENANT_ENVIRONMENT_{prefix}", "test")
    tenant = os.getenv(f"TENANT_{prefix}", "diku")
    USERNAME = os.getenv(f"FOLIO_USERNAME_{prefix}")
    SECRET = os.getenv(f"FOLIO_SECRET_{prefix}")
    auth_base_url: str = f"https://auth.{prefix.lower()}-{tenant_env}.bibliotek.sunet.se"
    api_base_url: str = f"https://api.{prefix.lower()}-{tenant_env}.bibliotek.sunet.se"
    
    print("auth_base_url:", auth_base_url)
    print("api_base_url:", api_base_url)
    
    if not USERNAME or not SECRET:
        raise SystemExit(f"FOLIO_USERNAME_{prefix} and FOLIO_SECRET_{prefix} must be set in .env")

    print("Initializing FOLIO API client...")
    print(f"Using username ({prefix}): {USERNAME}")
    print(f"Using secret {prefix}: {'*' * len(SECRET) if SECRET else 'None'}")

    client = FolioApiClient(
        username=USERNAME,
        secret=SECRET,
        auth_base_url=auth_base_url,
        api_base_url=api_base_url,
        realm=tenant,
        tenant=tenant,
    )
    manager = FolioUserManager(client)    
    
    # Create user test150 with admin role
    # user = manager.create_full_user(
    #     username="test_user_xxx",
    #     password="password",
    #     last_name="testlast",
    #     first_name="testfirst",
    #     email="test@example.com",
    #     admin_role=False,
    # )
    user = manager.create_full_user(
        username="benedith",
        password="Dm8Ys2NB8avU70hTz0kj6UWCOnSCA4kT",
        last_name="mulongo",
        first_name="ben",
        email="benedith@sunet.se",
        admin_role=False,
    )
    print(f"\nUser created successfully: {user['username']} (id: {user['id']})")
