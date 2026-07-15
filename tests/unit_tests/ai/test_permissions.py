# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
Authorization tests for the AI Integration permissions.

Verifies that:
- All 8 AI permissions are registered in FAB when the feature flag is enabled.
- No AI permissions are registered when the feature flag is disabled.
- `can_manage_ai_agents` is treated as admin-only.
- `can_manage_ai_agents` is the only AI permission restricted to administrators.
- Non-admin-only AI permissions (can_use_ai_chat, can_ai_*) are NOT in
  ADMIN_ONLY_PERMISSIONS, so they can be granted to other roles.
"""

from unittest.mock import MagicMock, patch

import pytest

from superset.extensions import appbuilder, feature_flag_manager
from superset.security.manager import SupersetSecurityManager
from tests.unit_tests.conftest import with_feature_flags

# The complete set of permissions the AI module must register.
AI_PERMISSIONS = {
    "can_use_ai_chat",
    "can_manage_ai_agents",
    "can_ai_run_sql",
    "can_ai_create_charts",
    "can_ai_edit_charts",
    "can_ai_create_dashboards",
    "can_ai_edit_dashboards",
    "can_ai_create_datasets",
}

# View menu used by all AI permissions.
AI_VIEW_MENU = "AIAgentResource"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pvm(permission_name: str, view_menu_name: str) -> MagicMock:
    """Build a minimal PermissionView mock understood by _is_admin_only."""
    pvm = MagicMock()
    pvm.permission.name = permission_name
    pvm.view_menu.name = view_menu_name
    return pvm


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


@with_feature_flags(ENABLE_AI_INTEGRATION=True)
def test_create_custom_permissions_registers_ai_perms_when_flag_enabled(
    app_context: None,
) -> None:
    """All 8 AI permissions must be registered when ENABLE_AI_INTEGRATION=True."""
    sm = SupersetSecurityManager(appbuilder)

    registered: list[tuple[str, str]] = []

    def record_perm(perm_name: str, view_menu_name: str) -> None:
        registered.append((perm_name, view_menu_name))

    with patch.object(sm, "add_permission_view_menu", side_effect=record_perm):
        sm.create_custom_permissions()

    ai_registered = {perm for perm, vm in registered if vm == AI_VIEW_MENU}
    assert ai_registered == AI_PERMISSIONS, (
        f"Missing AI permissions: {AI_PERMISSIONS - ai_registered}"
    )


@with_feature_flags(ENABLE_AI_INTEGRATION=False)
def test_create_custom_permissions_skips_ai_perms_when_flag_disabled(
    app_context: None,
) -> None:
    """No AI permissions must be registered when ENABLE_AI_INTEGRATION=False."""
    sm = SupersetSecurityManager(appbuilder)

    registered: list[tuple[str, str]] = []

    def record_perm(perm_name: str, view_menu_name: str) -> None:
        registered.append((perm_name, view_menu_name))

    with patch.object(sm, "add_permission_view_menu", side_effect=record_perm):
        sm.create_custom_permissions()

    ai_registered = {perm for perm, vm in registered if vm == AI_VIEW_MENU}
    assert ai_registered == set(), (
        f"AI permissions should NOT be registered when flag is off: {ai_registered}"
    )


# ---------------------------------------------------------------------------
# ADMIN_ONLY_PERMISSIONS tests
# ---------------------------------------------------------------------------


def test_can_manage_ai_agents_is_in_admin_only_permissions(
    app_context: None,
) -> None:
    """can_manage_ai_agents must live in ADMIN_ONLY_PERMISSIONS."""
    sm = SupersetSecurityManager(appbuilder)
    assert "can_manage_ai_agents" in sm.ADMIN_ONLY_PERMISSIONS


def test_other_ai_perms_not_in_admin_only_permissions(
    app_context: None,
) -> None:
    """Non-management AI permissions must NOT be in ADMIN_ONLY_PERMISSIONS
    so that admins can delegate them to other roles."""
    sm = SupersetSecurityManager(appbuilder)
    delegatable = AI_PERMISSIONS - {"can_manage_ai_agents"}
    for perm in delegatable:
        assert perm not in sm.ADMIN_ONLY_PERMISSIONS, (
            f"{perm!r} should be delegatable but is in ADMIN_ONLY_PERMISSIONS"
        )


# ---------------------------------------------------------------------------
# ADMIN_ONLY_VIEW_MENUS tests
# ---------------------------------------------------------------------------


def test_ai_agent_resource_is_not_admin_only_view_menu(
    app_context: None,
) -> None:
    """Delegable chat/tool permissions must not inherit an admin-only view menu."""
    sm = SupersetSecurityManager(appbuilder)
    assert AI_VIEW_MENU not in sm.ADMIN_ONLY_VIEW_MENUS


# ---------------------------------------------------------------------------
# _is_admin_only behavioural tests
# ---------------------------------------------------------------------------


def test_is_admin_only_returns_true_for_can_manage_ai_agents(
    app_context: None,
) -> None:
    """_is_admin_only must return True for can_manage_ai_agents/AIAgentResource."""
    sm = SupersetSecurityManager(appbuilder)
    pvm = _make_pvm("can_manage_ai_agents", AI_VIEW_MENU)
    assert sm._is_admin_only(pvm) is True


def test_is_admin_only_returns_false_for_delegable_ai_permissions(
    app_context: None,
) -> None:
    """Chat and tool permissions may be assigned to non-admin AI roles."""
    sm = SupersetSecurityManager(appbuilder)
    for perm in AI_PERMISSIONS - {"can_manage_ai_agents"}:
        pvm = _make_pvm(perm, AI_VIEW_MENU)
        assert sm._is_admin_only(pvm) is False, (
            f"_is_admin_only should return False for ({perm!r}, {AI_VIEW_MENU!r})"
        )


def test_is_admin_only_returns_false_for_non_ai_perm(
    app_context: None,
) -> None:
    """A regular non-admin permission must not be flagged as admin-only."""
    sm = SupersetSecurityManager(appbuilder)
    pvm = _make_pvm("can_read", "Chart")
    assert sm._is_admin_only(pvm) is False
