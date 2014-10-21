import urllib
from xbmctorrent import plugin
from xbmctorrent.scrapers import scraper
from xbmctorrent.ga import tracked
from xbmctorrent.caching import cached_route
from xbmctorrent.utils import ensure_fanart
from xbmctorrent.library import library_context


BASE_URL = "%s/" % plugin.get_setting("base_yify")
HEADERS = {
    "Referer": BASE_URL,
}
YOUTUBE_ACTION = "plugin://plugin.video.youtube/?path=/root/video&action=play_video&videoid=%s"
MOVIES_PER_PAGE = 20
GENRES = [
    "Action",
    "Adventure",
    "Animation",
    "Biography",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "Film-Noir",
    "Game-Show",
    "History",
    "Horror",
    "Music",
    "Musical",
    "Mystery",
    "News",
    "Reality-TV",
    "Romance",
    "Sci-Fi",
    "Sport",
    "Talk-Show",
    "Thriller",
    "War",
    "Western",
]
# Cache TTLs
DEFAULT_TTL = 24 * 3600 # 24 hours


@scraper("[COLOR yellow]YIFY Torrents - Movies [Pulsar mod][/COLOR]", "http://fbcdn-sphotos-h-a.akamaihd.net/hphotos-ak-frc3/204323_207963335901313_5804989_o.jpg")
@plugin.route("/yify")
@ensure_fanart
@tracked
def yify_index():
    return [
        {"label": "Search", "path": plugin.url_for("yify_search")},
        {"label": "Browse by Genre", "path": plugin.url_for("yify_genres")},

        {"label": "Most Popular", "path": plugin.url_for("yify_movies", sort="seeds", order="desc", quality="all", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 720p", "path": plugin.url_for("yify_movies", sort="seeds", order="desc", quality="720p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 1080p", "path": plugin.url_for("yify_movies", sort="seeds", order="desc", quality="1080p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 3D", "path": plugin.url_for("yify_movies", sort="seeds", order="desc", quality="3D", set=1, limit=MOVIES_PER_PAGE)},

        {"label": "Best Rated", "path": plugin.url_for("yify_movies", sort="rating", order="desc", quality="all", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 720p", "path": plugin.url_for("yify_movies", sort="rating", order="desc", quality="720p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 1080p", "path": plugin.url_for("yify_movies", sort="rating", order="desc", quality="1080p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 3D", "path": plugin.url_for("yify_movies", sort="rating", order="desc", quality="3D", set=1, limit=MOVIES_PER_PAGE)},

        {"label": "Most Recent", "path": plugin.url_for("yify_movies", sort="date", order="desc", quality="all", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 720p", "path": plugin.url_for("yify_movies", sort="date", order="desc", quality="720p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 1080p", "path": plugin.url_for("yify_movies", sort="date", order="desc", quality="1080p", set=1, limit=MOVIES_PER_PAGE)},
        {"label": "    in 3D", "path": plugin.url_for("yify_movies", sort="date", order="desc", quality="3D", set=1, limit=MOVIES_PER_PAGE)},
    ]


@library_context
def yify_show_data(callback):
    import xbmc
    import xbmcgui
    from contextlib import nested, closing
    from itertools import izip, chain
    from concurrent import futures
    from xbmctorrent import tmdb
    from xbmctorrent.utils import url_get_json, terminating, SafeDialogProgress

    plugin.set_content("movies")
    args = dict((k, v[0]) for k, v in plugin.request.args.items())

    current_page = int(args["set"])
    limit = int(args["limit"])

    with closing(SafeDialogProgress(delay_close=0)) as dialog:
        dialog.create(plugin.name)
        dialog.update(percent=0, line1="Fetching movie information...", line2="", line3="")

        try:
            search_result = url_get_json("%s/api/list.json" % BASE_URL, params=args, headers=HEADERS)
        except:
            plugin.notify("Unable to connect to %s." % BASE_URL)
            raise
        movies = search_result.get("MovieList") or []

        if not movies:
            return

        state = {"done": 0}
        def on_movie(future):
            data = future.result()
            state["done"] += 1
            dialog.update(
                percent=int(state["done"] * 100.0 / len(movies)),
                line2=data.get("title") or data.get("MovieTitleClean") or "",
            )

        with futures.ThreadPoolExecutor(max_workers=2) as pool_tmdb:
            tmdb_list = [pool_tmdb.submit(tmdb.get, movie["ImdbCode"]) for movie in movies]
            [future.add_done_callback(on_movie) for future in tmdb_list]
            while not all(job.done() for job in tmdb_list):
                if dialog.iscanceled():
                    return
                xbmc.sleep(100)

        tmdb_list = map(lambda job: job.result(), tmdb_list)
        for movie, tmdb_meta in izip(movies, tmdb_list):
            if tmdb_meta:
                magnet_link = urllib.quote_plus(movie["TorrentMagnetUrl"].encode("utf-8"))
                item = tmdb.get_list_item(tmdb_meta)
                if args.get("quality") == "all" and movie["Quality"] != "720p":
                    item["label"] = "%s (%s)" % (item["label"], movie["Quality"])
                item.update({
                    "path": "plugin://plugin.video.pulsar/play?uri=" + magnet_link,
                    # "path": plugin.url_for("play", uri=movie["TorrentMagnetUrl"]),
                    "is_playable": True,
                })
                item.setdefault("info", {}).update({
                    "count": movie["MovieID"],
                    "genre": "%s (%s S:%s P:%s)" % (item["info"]["genre"], movie["Size"], movie["TorrentSeeds"], movie["TorrentPeers"]),
                    "plot_outline": tmdb_meta["overview"],
                    "video_codec": "h264",
                })
                width = 1920
                height = 1080
                if movie["Quality"] == "720p":
                    width = 1280
                    height = 720
                item.setdefault("stream_info", {}).update({
                    "video": {
                        "codec": "h264",
                        "width": width,
                        "height": height,
                    },
                    "audio": {
                        "codec": "aac",
                    },
                })
                yield item

        if current_page < (int(search_result["MovieCount"]) / limit):
            next_args = args.copy()
            next_args["set"] = int(next_args["set"]) + 1
            yield {
                "label": ">> Next page",
                "path": plugin.url_for(callback, **next_args),
            }


@plugin.route("/yify/genres")
@ensure_fanart
@tracked
def yify_genres():
    for genre in GENRES:
        yield {
            "label": genre,
            "path": plugin.url_for("yify_genre", genre=genre, sort="seeds", order="desc", quality="all", set=1, limit=MOVIES_PER_PAGE),
        }


@plugin.route("/yify/genres/<genre>/<set>")
@cached_route(ttl=DEFAULT_TTL, content_type="movies")
@ensure_fanart
@tracked
def yify_genre(genre, set):
    plugin.request.args.update({
        "genre": [genre],
        "set": [set],
    })
    return yify_show_data("yify_genre")


@plugin.route("/yify/browse/<sort>/<quality>/<set>")
@cached_route(ttl=DEFAULT_TTL, content_type="movies")
@ensure_fanart
@tracked
def yify_movies(sort, quality, set):
    plugin.request.args.update({
        "sort": [sort],
        "quality": [quality],
        "set": [set],
    })
    return yify_show_data("yify_movies")


@plugin.route("/yify/search")
@tracked
def yify_search():
    query = plugin.request.args.get("query")
    if query:
        query = query[0]
    else:
        query = plugin.keyboard("", "XBMCtorrent - YIFY - Search")
    if query:
        plugin.redirect(plugin.url_for("yify_search_query", keywords=query, quality="all", set=1, limit=MOVIES_PER_PAGE))


@plugin.route("/yify/search/<keywords>/<set>")
@cached_route(ttl=DEFAULT_TTL, content_type="movies")
@ensure_fanart
@tracked
def yify_search_query(keywords, set):
    plugin.request.args.update({
        "keywords": [keywords],
        "set": [set],
    })
    return yify_show_data("yify_search_query")
