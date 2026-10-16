---
title: "Query accuracy"
description: "The cases where Logfire query results can differ from what the SQL alone suggests, and what to do about them."
---

# Query accuracy

Most Logfire queries return exact results. This page lists the cases where they do not, so that you know when to expect a difference.

## Text search skips long words

Text search operations (`LIKE`, `ILIKE`, regular expressions, and full-text search) skip words that are 40 bytes or longer. A word is a run of letters and digits. Any other character, for example a space, `-`, `_`, `.`, `:` or `/`, ends the word.

This works for most common values, because they split into short words:

| Value | Words |
| --- | --- |
| `550e8400-e29b-41d4-a716-446655440000` (UUID) | `550e8400`, `e29b`, `41d4`, `a716`, `446655440000` |
| `2026-10-14T09:30:00Z` (date and time) | `2026`, `10`, `14T09`, `30`, `00Z` |
| `connection refused by db-primary` | `connection`, `refused`, `by`, `db`, `primary` |

It does not work for long values that have no separators, for example hashes, API keys, tokens and base64-encoded data (binary data written as text). A search can miss a record when the text that you search for is only part of such a value.

For example, a SHA-256 (Secure Hash Algorithm 256) hash such as `9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08` is one word of 64 bytes. `message LIKE '%9f86d081%'` can miss the record that contains it.

A value that has a prefix keeps the prefix searchable. For `service_9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08`, the word `service` is found, but a search for part of the hash can miss the record.

To find a record by a long value of this type, send the value as its own attribute and compare the full value with `=`. For example, `attributes->>'commit_sha' = '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'`.
