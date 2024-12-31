::: logfire
    options:
        show_root_toc_entry: false
        members: false


::: logfire.Logfire
    options:
        show_root_heading: true
        show_root_full_path: false
        exclude:
        filters:
            - "!instrument_redis"
            - "!instrument_pymongo"
            - "!^with_trace_sample_rate$"
            - "!^_[^_]"


::: logfire
    options:
        show_root_toc_entry: false
        show_docstring_description: true
        filters: ["!^Logfire$", "!^_[^_]"]
