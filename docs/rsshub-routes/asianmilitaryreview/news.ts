import { load } from 'cheerio';
import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/asianmilitaryreview/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.asianmilitaryreview.com/',
};

async function handler(): Promise<Data> {
    const base = 'https://www.asianmilitaryreview.com/';
    const html = await ofetch(base);
    const $ = load(html);
    const nav = /(^|\/)(about|contact|privacy|terms|category|categories|tag|tags|author|policy|legal|advertise|subscribe|newsletter|podcast|video|search|login|signup)(\/|$)/;
    const items = $('h2 a, h3 a')
        .toArray()
        .map((el) => ({
            href: $(el).attr('href')?.trim() ?? '',
            title: $(el).text().trim(),
        }))
        .filter((x) => x.title.length > 12 && x.href && !x.href.startsWith('#') && !x.href.startsWith('javascript') && !nav.test(x.href));
    return {
        title: 'Asian Military Review News',
        link: base,
        item: items.map((x) => ({
            title: x.title,
            link: x.href.startsWith('http') ? x.href : new URL(x.href, base).toString(),
        })),
    };
}
