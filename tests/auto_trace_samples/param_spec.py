def check_param_spec_syntax[**P](*args: P.args, **kwargs: P.kwargs):
    return args, kwargs
