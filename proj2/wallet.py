"""
The customer's wallet: charging it for an order and refunding a cancelled one.

Balances are whole cents in ``User.wallet``. Both functions take a connection and are
meant to run inside ``proj2.db.transaction()`` together with the order they belong to, so
a wallet is never charged without its order, or an order stored without its charge.

An order records what it took as ``wallet_cents`` in its details. Refunds read that
rather than the order's total, because orders placed before wallets were charged took
nothing and must give nothing back.
"""

import json

from proj2.sqlQueries import execute_query, fetch_one


class InsufficientFundsError(Exception):
    """The wallet holds less than the order costs."""

    def __init__(self, balance_cents: int, total_cents: int):
        super().__init__(f"wallet holds {balance_cents} cents, order costs {total_cents}")
        self.balance_cents = balance_cents
        self.total_cents = total_cents
        self.message = (
            f"Your wallet has ${balance_cents / 100:.2f}; this order is ${total_cents / 100:.2f}."
        )


def to_cents(dollars) -> int:
    """
    A dollar amount, as the order code computes them, in whole cents
    Args:
        dollars (float): The amount, already rounded to cents.
    Returns:
        int: The amount in cents.
    """
    return int(round(float(dollars) * 100))


def balance_cents(conn, usr_id) -> int:
    """
    What a customer's wallet holds
    Args:
        conn (sqlite3.Connection): Open database connection.
        usr_id (int): The customer.
    Returns:
        int: The balance in cents, 0 if there is no such customer.
    """
    row = fetch_one(conn, 'SELECT wallet FROM "User" WHERE usr_id = ?', (usr_id,))
    return int(row[0] or 0) if row else 0


def charge(conn, usr_id, cents: int) -> None:
    """
    Take an order's total out of the customer's wallet

    The balance check and the withdrawal are one statement, so two orders placed at the
    same moment cannot both spend the same money.
    Args:
        conn (sqlite3.Connection): Open database connection.
        usr_id (int): The customer.
        cents (int): The order's total.
    Raises:
        ValueError: cents is negative, which would pay the customer instead.
        InsufficientFundsError: The wallet holds less than cents; nothing was taken.
    """
    if cents < 0:
        raise ValueError("an order cannot cost less than nothing")
    taken = execute_query(
        conn,
        'UPDATE "User" SET wallet = wallet - ? WHERE usr_id = ? AND wallet >= ?',
        (cents, usr_id, cents),
    )
    if taken.rowcount != 1:
        raise InsufficientFundsError(balance_cents(conn, usr_id), cents)


def refund_order(conn, usr_id, details) -> int:
    """
    Give back whatever an order took from the customer's wallet
    Args:
        conn (sqlite3.Connection): Open database connection.
        usr_id (int): The customer.
        details (str | None): The order's stored details JSON.
    Returns:
        int: The cents returned, 0 for an order that never charged the wallet.
    """
    try:
        cents = int(json.loads(details or "{}").get("wallet_cents") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0
    if cents <= 0:
        return 0
    execute_query(conn, 'UPDATE "User" SET wallet = wallet + ? WHERE usr_id = ?', (cents, usr_id))
    return cents
