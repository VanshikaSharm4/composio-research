# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import Optional

from .._models import BaseModel

__all__ = ["ConnectedAccountDeleteResponse"]


class ConnectedAccountDeleteResponse(BaseModel):
    """Response returned after successfully deleting a connected account"""

    success: bool
    """Indicates whether the connected account was successfully deleted"""

    revoke_job_id: Optional[str] = None
    """Identifier of the background revoke job started for this delete.

    Present only when `revoke_on_delete=true`. Track the job and its per-connection
    results from the Composio dashboard — a programmatic endpoint to poll this job
    is not yet generally available.
    """
