import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/articles',
    categories: ['government'],
    example: '/brookings/articles',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    name: 'Articles',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.brookings.edu/',
};

async function handler(): Promise<Data> {
    // Brookings 首页 — 文章 URL 模式 /articles/<slug>/
    const listUrl = 'https://www.brookings.edu/';
    const html = await ofetch(listUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        },
        parseResponse: (t: string) => t,
    });
    const $ = load(html);

    const items = $('a[href*="/articles/"]')
        .toArray()
        .map((el) => {
            const $a = $(el);
            return {
                href: $a.attr('href')?.trim() ?? '',
                title: $a.text().trim(),
            };
        })
        .filter((x) => x.href.match(/\/articles\/[a-z0-9-]+/) && x.title.length > 20);

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
        title: 'Brookings Institution Articles',
        link: listUrl,
        item: uniq.map((x) => ({
            title: x.title,
            link: new URL(x.href, listUrl).toString(),
        })),
    };
}
