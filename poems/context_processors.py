from poems.models import public_collections


def public_navigation(_request):
    return {"public_collections": public_collections()}
