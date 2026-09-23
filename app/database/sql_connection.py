import os
import struct
from contextlib import contextmanager
from typing import Iterator

import pyodbc
from azure.identity import (
    AzureCliCredential,
    DefaultAzureCredential,
)


SQL_COPT_SS_ACCESS_TOKEN = 1256

SQL_TOKEN_SCOPE = (
    "https://database.windows.net/.default"
)


def database_mode() -> str:
    """Return the selected database environment."""
    return os.getenv(
        "DATABASE_MODE",
        "local_sqlserver",
    ).strip().lower()


def validate_driver(
    driver: str,
) -> str:
    """Ensure the configured ODBC driver is installed."""
    installed_drivers = pyodbc.drivers()

    if driver not in installed_drivers:
        raise RuntimeError(
            "Configured ODBC driver is not installed. "
            f"Configured: {driver!r}. "
            f"Installed: {installed_drivers!r}."
        )

    return driver


def build_local_connection_string() -> str:
    """Build a connection string for local SQL Server."""

    driver = validate_driver(
        os.getenv(
            "LOCAL_SQL_DRIVER",
            "ODBC Driver 18 for SQL Server",
        ).strip()
    )

    server = os.getenv(
        "LOCAL_SQL_SERVER",
        "localhost",
    ).strip()

    database = os.getenv(
        "LOCAL_SQL_DATABASE",
        "transition_knowledge_db",
    ).strip()

    trusted_connection = os.getenv(
        "LOCAL_SQL_TRUSTED_CONNECTION",
        "yes",
    ).strip()

    encrypt = os.getenv(
        "LOCAL_SQL_ENCRYPT",
        "yes",
    ).strip()

    trust_certificate = os.getenv(
        "LOCAL_SQL_TRUST_SERVER_CERTIFICATE",
        "yes",
    ).strip()

    timeout = os.getenv(
        "LOCAL_SQL_CONNECTION_TIMEOUT",
        "30",
    ).strip()

    return (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"Database={database};"
        f"Trusted_Connection={trusted_connection};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_certificate};"
        f"Connection Timeout={timeout};"
    )


def build_azure_connection_string() -> str:
    """Build an encrypted Azure SQL connection string."""

    driver = validate_driver(
        os.getenv(
            "AZURE_SQL_ODBC_DRIVER",
            "ODBC Driver 18 for SQL Server",
        ).strip()
    )

    server = os.environ[
        "AZURE_SQL_SERVER"
    ].strip()

    database = os.environ[
        "AZURE_SQL_DATABASE"
    ].strip()

    port = os.getenv(
        "AZURE_SQL_PORT",
        "1433",
    ).strip()

    encrypt = os.getenv(
        "AZURE_SQL_ENCRYPT",
        "yes",
    ).strip()

    trust_certificate = os.getenv(
        "AZURE_SQL_TRUST_SERVER_CERTIFICATE",
        "no",
    ).strip()

    timeout = os.getenv(
        "AZURE_SQL_CONNECTION_TIMEOUT",
        "30",
    ).strip()

    return (
        f"Driver={{{driver}}};"
        f"Server=tcp:{server},{port};"
        f"Database={database};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_certificate};"
        f"Connection Timeout={timeout};"
    )


def create_azure_credential():
    """
    Use Azure CLI during local Azure testing and managed
    identity after deployment.
    """
    environment = os.getenv(
        "AGENTIC_BLUEPRINT_ENVIRONMENT",
        "development",
    ).strip().lower()

    if environment == "development":
        return AzureCliCredential()

    client_id = os.getenv(
        "AZURE_CLIENT_ID",
        "",
    ).strip()

    return DefaultAzureCredential(
        managed_identity_client_id=(
            client_id or None
        ),
        exclude_interactive_browser_credential=True,
    )


def build_access_token() -> bytes:
    """Create the access-token structure required by pyodbc."""

    credential = create_azure_credential()

    try:
        token = credential.get_token(
            SQL_TOKEN_SCOPE
        ).token
    finally:
        credential.close()

    token_bytes = token.encode(
        "utf-16-le"
    )

    return struct.pack(
        f"<I{len(token_bytes)}s",
        len(token_bytes),
        token_bytes,
    )


def create_connection() -> pyodbc.Connection:
    """Connect to either local SQL Server or Azure SQL."""

    mode = database_mode()

    if mode == "local_sqlserver":
        
        try:
            return pyodbc.connect(
                build_local_connection_string()
            )

        except pyodbc.Error as error:
            raise RuntimeError(
                "Local SQL Server connection failed. "
                "Verify LOCAL_SQL_SERVER, "
                "LOCAL_SQL_DATABASE, Windows authentication, "
                "SQL Server service status, and ODBC Driver 18."
            ) from error

    if mode == "azure_sql":
        print(
            "Selected database mode:",
            mode,
        )

        connection_string = (
            build_azure_connection_string()
        )

        auth_mode = os.getenv(
            "AZURE_SQL_AUTH_MODE",
            "entra",
        ).strip().lower()

        try:
            if auth_mode == "entra":
                return pyodbc.connect(
                    connection_string,
                    attrs_before={
                        SQL_COPT_SS_ACCESS_TOKEN: (
                            build_access_token()
                        )
                    },
                )

            if auth_mode == "password":
                username = os.environ[
                    "AZURE_SQL_USERNAME"
                ]

                password = os.environ[
                    "AZURE_SQL_PASSWORD"
                ]

                return pyodbc.connect(
                    connection_string
                    + f"UID={username};"
                    + f"PWD={password};"
                )

        except pyodbc.Error as error:
            raise RuntimeError(
                "Azure SQL connection failed. "
                "Verify Azure SQL networking, identity, "
                "database permissions, and configuration."
            ) from error

        raise ValueError(
            "AZURE_SQL_AUTH_MODE must be "
            "'entra' or 'password'."
        )

    raise ValueError(
        "DATABASE_MODE must be "
        "'local_sqlserver' or 'azure_sql'. "
        f"Received: {mode!r}"
    )


@contextmanager
def database_connection() -> Iterator[
    pyodbc.Connection
]:
    """Open and safely close a database connection."""

    connection = create_connection()

    try:
        yield connection
    finally:
        connection.close()