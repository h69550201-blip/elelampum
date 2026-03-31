(function () {
    'use strict';

    var PLUGIN_NAME = 'BurstBridge';
    var PLUGIN_VERSION = '1.0.0';

    var DEFAULT_API_URL = '';

    function getApiUrl() {
        var url = Lampa.Storage.get('burst_bridge_url', '') || DEFAULT_API_URL;
        if (url && url.indexOf('://') === -1) url = 'http://' + url;
        return url.replace(/\/$/, '');
    }

    function setApiUrl(url) {
        Lampa.Storage.set('burst_bridge_url', url);
    }

    function getEnabledProviders() {
        var val = Lampa.Storage.get('burst_bridge_providers', '');
        if (!val || val === 'undefined') return '';
        return val;
    }

    function setEnabledProviders(val) {
        Lampa.Storage.set('burst_bridge_providers', val);
    }

    function getTimeout() {
        return Lampa.Storage.get('burst_bridge_timeout', 15);
    }

    function formatSize(sizeStr) {
        if (!sizeStr) return '';
        return sizeStr;
    }

    function buildSearchParams(card, search_type) {
        var params = {
            type: search_type || 'general',
            timeout: getTimeout()
        };

        var providers = getEnabledProviders();
        if (providers) params.providers = providers;

        if (typeof card === 'string') {
            params.query = card;
            params.title = card;
            return params;
        }

        if (card.title) params.title = card.title;
        if (card.original_title) params.original_title = card.original_title;
        if (card.name) params.title = params.title || card.name;
        if (card.original_name) params.original_title = params.original_title || card.original_name;

        var year = '';
        if (card.release_date) year = card.release_date.substr(0, 4);
        else if (card.first_air_date) year = card.first_air_date.substr(0, 4);
        if (year) params.year = year;

        if (card.imdb_id) params.imdb_id = card.imdb_id;
        else if (card.external_ids && card.external_ids.imdb_id) params.imdb_id = card.external_ids.imdb_id;

        if (card.season) params.season = card.season;
        if (card.episode) params.episode = card.episode;

        if (!params.query) {
            params.query = params.original_title || params.title || '';
        }

        return params;
    }

    function searchTorrents(card, search_type, callback) {
        var apiUrl = getApiUrl();
        if (!apiUrl) {
            Lampa.Noty.show('Burst Bridge: Set API URL in settings');
            callback([]);
            return;
        }

        var params = buildSearchParams(card, search_type);

        var queryParts = [];
        for (var key in params) {
            if (params.hasOwnProperty(key) && params[key] !== '' && params[key] !== undefined) {
                queryParts.push(encodeURIComponent(key) + '=' + encodeURIComponent(params[key]));
            }
        }

        var url = apiUrl.replace(/\/$/, '') + '/api/search?' + queryParts.join('&');

        Lampa.Reguest.clear('burst_bridge');

        var network = new Lampa.Reguest();
        network.timeout(getTimeout() * 1000 + 5000);
        network.silent(
            url,
            function (response) {
                var results = [];
                if (response && response.results) {
                    response.results.forEach(function (item) {
                        results.push({
                            title: item.name || 'Unknown',
                            quality: extractQuality(item.name),
                            size: formatSize(item.size),
                            seeds: item.seeds || 0,
                            peers: item.peers || 0,
                            hash: item.info_hash || '',
                            magnet: item.magnet || '',
                            tracker: item.provider || 'Burst',
                            _burst: true
                        });
                    });
                }
                callback(results);
            },
            function (error) {
                Lampa.Noty.show('Burst Bridge: Search error');
                callback([]);
            },
            false,
            {
                dataType: 'json',
                headers: { 'Accept': 'application/json' }
            }
        );
    }

    function extractQuality(name) {
        if (!name) return '';
        name = name.toUpperCase();
        if (name.indexOf('2160P') >= 0 || name.indexOf('4K') >= 0 || name.indexOf('UHD') >= 0) return '4K';
        if (name.indexOf('1080P') >= 0 || name.indexOf('FULLHD') >= 0) return '1080p';
        if (name.indexOf('720P') >= 0 || name.indexOf('HD') >= 0) return '720p';
        if (name.indexOf('480P') >= 0) return '480p';
        if (name.indexOf('BDREMUX') >= 0 || name.indexOf('REMUX') >= 0) return 'Remux';
        if (name.indexOf('BDRIP') >= 0) return 'BDRip';
        if (name.indexOf('WEBRIP') >= 0 || name.indexOf('WEB-DL') >= 0) return 'WEB';
        if (name.indexOf('HDTV') >= 0) return 'HDTV';
        if (name.indexOf('HDRIP') >= 0) return 'HDRip';
        if (name.indexOf('CAM') >= 0) return 'CAM';
        return '';
    }

    function addSettings() {
        Lampa.SettingsApi.addParam({
            component: 'burst_bridge',
            param: {
                name: 'burst_bridge_url',
                type: 'input',
                values: '',
                default: ''
            },
            field: {
                name: 'Burst Bridge URL',
                description: 'Backend API address (e.g. https://your-server.railway.app)'
            }
        });

        Lampa.SettingsApi.addParam({
            component: 'burst_bridge',
            param: {
                name: 'burst_bridge_providers',
                type: 'input',
                values: '',
                default: ''
            },
            field: {
                name: 'Providers',
                description: 'Comma-separated provider IDs (empty = defaults: 1337x, yts, bt4g, knaben, thepiratebay, torrentio)'
            }
        });

        Lampa.SettingsApi.addParam({
            component: 'burst_bridge',
            param: {
                name: 'burst_bridge_timeout',
                type: 'select',
                values: {
                    10: '10 sec',
                    15: '15 sec',
                    20: '20 sec',
                    30: '30 sec'
                },
                default: 15
            },
            field: {
                name: 'Search Timeout',
                description: 'Maximum time to wait for provider responses'
            }
        });
    }

    function initTorrentSource() {
        Lampa.Params.select('source', 'burst_bridge', 'Burst Bridge');

        if (Lampa.Api && Lampa.Api.sources) {
            Lampa.Api.sources.burst_bridge = {
                search: function (card, type) {
                    return new Promise(function (resolve) {
                        var search_type = 'general';
                        if (card && card.number_of_seasons) search_type = 'episode';
                        else if (type === 'movie') search_type = 'movie';
                        else if (type === 'tv') search_type = 'episode';

                        searchTorrents(card, search_type, function (results) {
                            resolve(results);
                        });
                    });
                }
            };
        }
    }

    function interceptTorrentSearch() {
        Lampa.Listener.follow('torrent', function (e) {
            if (e.type === 'search') {
                var apiUrl = getApiUrl();
                if (!apiUrl) return;

                var card = e.card || {};
                var search_type = 'general';

                if (card.number_of_seasons) {
                    search_type = card.episode ? 'episode' : 'season';
                } else if (card.release_date || card.budget !== undefined) {
                    search_type = 'movie';
                }

                searchTorrents(card, search_type, function (results) {
                    if (e.callback && typeof e.callback === 'function') {
                        e.callback(results);
                    }
                });
            }
        });
    }

    function createComponent() {
        Lampa.Component.add('burst_bridge_search', {
            create: function () {
                this.activity = Lampa.Activity.active();
            },
            start: function () {
                var _this = this;
                var query = this.activity.query || '';

                searchTorrents(query, 'general', function (results) {
                    _this.results = results;
                    _this.render();
                });
            },
            render: function () {
                var html = '<div class="burst-results">';
                if (this.results && this.results.length) {
                    this.results.forEach(function (r, i) {
                        html += '<div class="burst-item selector" data-index="' + i + '">';
                        html += '<div class="burst-name">' + r.title + '</div>';
                        html += '<div class="burst-meta">';
                        if (r.quality) html += '<span class="burst-quality">' + r.quality + '</span>';
                        if (r.size) html += '<span class="burst-size">' + r.size + '</span>';
                        html += '<span class="burst-seeds">↑' + r.seeds + '</span>';
                        html += '<span class="burst-peers">↓' + r.peers + '</span>';
                        html += '<span class="burst-tracker">' + r.tracker + '</span>';
                        html += '</div></div>';
                    });
                } else {
                    html += '<div class="burst-empty">No torrents found</div>';
                }
                html += '</div>';
                this.activity.render().html(html);
                Lampa.Controller.toggle('content');
            },
            pause: function () {},
            stop: function () {},
            destroy: function () {}
        });
    }

    var css = "\n    .burst-results { padding: 1em; }\n    .burst-item {\n        padding: 0.8em 1em;\n        margin-bottom: 0.3em;\n        border-radius: 0.5em;\n        background: rgba(255,255,255,0.05);\n        cursor: pointer;\n    }\n    .burst-item.focus,\n    .burst-item:hover {\n        background: rgba(255,255,255,0.15);\n    }\n    .burst-name {\n        font-size: 1.05em;\n        margin-bottom: 0.3em;\n        word-break: break-word;\n    }\n    .burst-meta {\n        display: flex;\n        flex-wrap: wrap;\n        gap: 0.8em;\n        font-size: 0.85em;\n        opacity: 0.7;\n    }\n    .burst-quality {\n        color: #4CAF50;\n        font-weight: bold;\n    }\n    .burst-seeds { color: #8BC34A; }\n    .burst-peers { color: #FF9800; }\n    .burst-tracker { color: #00BCD4; }\n    .burst-empty {\n        text-align: center;\n        padding: 3em;\n        opacity: 0.5;\n    }\n    ";

    function init() {
        var style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);

        if (Lampa.Storage.get('burst_bridge_providers', '') === undefined ||
            Lampa.Storage.get('burst_bridge_providers', '') === 'undefined') {
            Lampa.Storage.set('burst_bridge_providers', '');
        }

        if (Lampa.SettingsApi) {
            Lampa.SettingsApi.addComponent({
                component: 'burst_bridge',
                name: 'Burst Bridge',
                icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
            });
            addSettings();
        }

        createComponent();
        initTorrentSource();
        interceptTorrentSearch();

        Lampa.Manifest.plugins = Lampa.Manifest.plugins || {};
        Lampa.Manifest.plugins[PLUGIN_NAME] = {
            name: PLUGIN_NAME,
            version: PLUGIN_VERSION,
            description: 'Torrent search via Elementum Burst providers'
        };

        console.log('[BurstBridge] Plugin loaded v' + PLUGIN_VERSION);
    }

    if (window.appready) {
        init();
    } else {
        Lampa.Listener.follow('app', function (e) {
            if (e.type === 'ready') init();
        });
    }

})();
