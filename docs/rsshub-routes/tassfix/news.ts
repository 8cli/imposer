import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/tassfix/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://tass.com/',
};

async function handler(): Promise<Data> {
    const html = await ofetch('https://tass.com/');
    const $ = load(html);
    const base = 'https://tass.com';
    const nav = /(^|\/)(about|contact|privacy|terms|rss|search|login|signup|section|politics|business|economy|oil|world)(\/|$)/;
    const items = $('a')
        .toArray()
        .map((el) => ({ href: $(el).attr('href')?.trim() ?? '', title: $(el).text().trim() }))
        .filter((x) => x.title.length > 15 && x.href.startsWith('/') && !nav.test(x.href));
    return {
        title: 'TASS News',
        link: 'https://tass.com/',
        item: items.map((x) => ({ title: x.title, link: base + x.href })),
    };
}
