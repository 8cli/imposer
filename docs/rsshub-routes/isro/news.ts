import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/news',
    categories: ['technology'],
    example: '/isro/news',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.isro.gov.in/',
};

async function handler(): Promise<Data> {
    // ISRO 首页 — 相对路径文章（如 First_private_orbital_launch_lifts_from_Sriharikota.html）
    const listUrl = 'https://www.isro.gov.in/';
    const html = await ofetch(listUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        },
        parseResponse: (t: string) => t,
    });
    const $ = load(html);

    const items = $('a[href$=".html"]')
        .toArray()
        .map((el) => {
            const $a = $(el);
            const href = $a.attr('href')?.trim() ?? '';
            return {
                href,
                title: $a.text().trim(),
            };
        })
        .filter((x) => x.title.length > 15 && !x.href.startsWith('http') && !x.href.includes('media_isro') && !x.href.includes('pdf'));

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
        title: 'ISRO News',
        link: listUrl,
        item: uniq.map((x) => ({
            title: x.title,
            link: new URL(x.href, listUrl).toString(),
        })),
    };
}
