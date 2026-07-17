from logfire._internal.db_statement_summary import MAX_QUERY_MESSAGE_LENGTH, message_from_db_statement


def test_no_db_statement():
    assert message_from_db_statement({}, None, 'x') is None


def test_short_db_statement():
    assert message_from_db_statement({'db.statement': 'SELECT * FROM table'}, None, 'x') == 'SELECT * FROM table'


def test_message_same():
    assert (
        message_from_db_statement({'db.statement': 'SELECT * FROM table'}, 'SELECT', 'SELECT') == 'SELECT * FROM table'
    )


def test_message_different():
    assert message_from_db_statement({'db.statement': 'SELECT * FROM table'}, 'SELECT', 'x') is None


def test_message_not_in_db_statement():
    q = 'SELECT apple, banana, carrot, durian, egg, fig FROM table WHERE apple = 1'
    assert message_from_db_statement({'db.statement': q}, 'not in statement', 'not in statement') is None


def test_message_multiword():
    q = 'SELECT apple, banana, carrot, durian, egg, fig FROM table WHERE apple = 1'
    assert message_from_db_statement({'db.statement': q}, 'SELECT apple', 'SELECT apple') is None


def test_ok_after_clean():
    q = """
-- this is a long comment about the sql
SELECT apple, banana, carrot, durian, egg, fig FROM table
"""
    # insert_assert(message_from_db_statement({'db.statement': q}, None, 'x'))
    assert (
        message_from_db_statement({'db.statement': q}, None, 'x')
        == 'SELECT apple, banana, carrot, durian, egg, fig FROM table'
    )


def attrs(q: str):
    return {'db.statement': q, 'db.system': 'postgresql'}


def test_query_rewritten():
    q = 'SELECT apple, banana, carrot, durian, egg, fig FROM table WHERE apple = 1 and banana = 2'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT apple, ban…, egg, fig FROM table WHERE …'


def test_invalid_sql():
    q = 'SELECT apple, banana, carrot, durian, egg, fig FROM "table WHERE apple = 1 offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT apple, ban…, egg, fig FROM "table WHERE …'


def test_one_cte():
    q = 'WITH foobar AS (SELECT apple, banana, carrot, durian FROM table) SELECT * FROM foobar where x = 1'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'WITH foobar AS (…) SELECT * FROM foobar WHERE …'


def test_one_cte_long():
    q = 'WITH foobar_foobar_foobar AS (SELECT apple, banana, carrot FROM table) SELECT * FROM foobar where x = 1'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'WITH fooba…oobar AS (…) SELECT * FROM foobar WHERE …'


def test_two_ctes():
    q = 'WITH foo AS (SELECT * FROM table), bar AS (SELECT apple, banana, carrot, durian FROM foo) SELECT * FROM bar'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'WITH …[2 CTEs] SELECT * FROM bar'


def test_long_select():
    q = '\nSELECT apple, banana, carrot, durian, egg, fig, grape FROM table offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT apple, ban…fig, grape FROM table'


def test_from_subquery():
    q = 'select * from (select * from table) as sub where aaaaa_bbbb_cccccc=1 offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT * FROM (select * from table) AS sub WHERE …'


def test_from_quoted():
    q = 'select * from "foo.bar" as sub where aaaaa_bbbb_cccccc=1 offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT * FROM "foo.bar" WHERE …'


def test_from_long():
    q = 'select * from "aaaaa.bbbb.cccccc" as sub where aaaaa_bbbb_cccccc=1 offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT * FROM "aaaaa.bbbb.cccccc" WHERE …'


def test_one_join():
    q = '  SELECT apple, banana, carrot FROM table JOIN other ON table.id = other.id offset 12345678901234567890'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert (
        message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT apple, ban…na, carrot FROM table JOIN other ON …'
    )


def test_one_join_long():
    q = '  SELECT apple, banana, carrot FROM table JOIN other_other_other ON table.id = other_other_other.id'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert (
        message_from_db_statement(attrs(q), None, 'SELECT')
        == 'SELECT apple, ban…na, carrot FROM table JOIN other…other ON …'
    )


def test_two_joins():
    q = 'SELECT * FROM table JOIN other ON table.id = other.id JOIN another ON table.id = another.id'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT * FROM table …[2 JOINs]'


def test_where():
    q = 'SELECT apple, banana, carrot, durian, egg FROM table where a = 1 and b = 2 and c =3'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert message_from_db_statement(attrs(q), None, 'SELECT') == 'SELECT apple, ban…urian, egg FROM table WHERE …'


def test_limit():
    q = 'SELECT apple, banana, carrot, durian, egg, fig, grape FROM table where apple=12345678901234567890 limit 10'
    # insert_assert(message_from_db_statement(attrs(q), None, 'SELECT'))
    assert (
        message_from_db_statement(attrs(q), None, 'SELECT')
        == 'SELECT apple, ban…fig, grape FROM table WHERE … LIMIT 10'
    )


def test_update():
    q = 'UPDATE table set apple = 1 where banana = 2 and carrrrrrrot = 3 and durian = 4 and egg = 5 and fig = 6'
    # insert_assert(message_from_db_statement(attrs(q), None, 'UPDATE'))
    assert (
        message_from_db_statement(attrs(q), None, 'UPDATE')
        == 'UPDATE table set apple = 1 where banan … and durian = 4 and egg = 5 and fig = 6'
    )


def test_insert():
    q = 'INSERT INTO table (apple, banana, carrot, durian, egg, fig) VALUES (1, 2, 3, 4, 5, 6)'
    # insert_assert(message_from_db_statement(attrs(q), None, 'INSERT'))
    assert (
        message_from_db_statement(attrs(q), None, 'INSERT')
        == 'INSERT INTO table (apple, bana…n, egg, fig) VALUES (1, 2, 3, 4, 5, 6)'
    )


def test_insert_long_table():
    # The table name isn't truncated on its own, so this was 112 chars before the bound.
    q = 'INSERT INTO "analytics"."very_long_events_table_name_for_testing" (apple, banana, carrot, durian, egg, fig) VALUES (1, 2, 3, 4, 5, 6)'
    # insert_assert(message_from_db_statement(attrs(q), None, 'INSERT'))
    result = message_from_db_statement(attrs(q), None, 'INSERT')
    assert result == 'INSERT INTO "analytics"."very_long_event…a…n, egg, fig) VALUES (1, 2, 3, 4, 5, 6)'
    # +1: truncate() returns 2 * (length // 2) + 1 chars for even lengths, as it does for SELECT.
    assert len(result) <= MAX_QUERY_MESSAGE_LENGTH + 1
