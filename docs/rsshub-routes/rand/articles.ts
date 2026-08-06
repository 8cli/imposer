import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/articles',
    categories: ['government'],
    example: '/rand/articles',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    name: 'Research & Commentary',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.rand.org/',
};

async function handler(): Promise<Data> {
    // RAND 首页 — 文章 URL 模式 /pubs/articles/2026/<slug>.html
    const listUrl = 'https://www.rand.org/';
    const html = await ofetch(listUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        },
        parseResponse: (t: string) => t,
    });
    const $ = load(html);

    const items = $('a[href*="/pubs/"]')
        .toArray()
        .map((el) => {
            const $a = $(el);
            return {
                href: $a.attr('href')?.trim() ?? '',
                title: $a.text().trim(),
            };
        })
        .filter((x) => x.href.match(/\/pubs\/(articles|commentary)\/20\d\d\//) && x.title.length > 20);

    const seen = new Set<string>();
    const uniq = items.filter((x) => {
        const key = x.href;
        if (seen.has(key)) {
            return false;
        }
        seen.add(key);
        return true;
    });

    return {
        title: 'RAND Research & Commentary',
        link: listUrl,
        item: uniq.map((x) => ({
            title: x.title,
            link: new URL(x.href, listUrl).toString(),
        })),
    };
}
