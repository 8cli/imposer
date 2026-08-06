import { load } from 'cheerio';
import type { Context } from 'hono';

import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';
import { parseDate } from '@/utils/parse-date';

export const route: Route = {
    path: '/newsroom',
    categories: ['traditional-media'],
    example: '/esa/newsroom',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    radar: [
        {
            source: ['www.esa.int/Newsroom'],
            target: '/newsroom',
        },
    ],
    name: 'Newsroom (Press Releases)',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.esa.int/Newsroom',
};

async function handler(): Promise<Data> {
    const listUrl = 'https://www.esa.int/Newsroom';
    const html = await ofetch(listUrl);
    const $ = load(html);

    const items = $('div.grid-item.press-release')
        .toArray()
        .map((el) => {
            const $item = $(el);
            const $a = $item.find('a.card.press-release');
            return {
                href: $a.attr('href')?.trim() ?? '',
                title: $item.find('h3.heading').text().trim(),
                date: $item.attr('data-date'),
            };
        })
        .filter((x) => x.href.startsWith('/Newsroom/Press_Releases/') && x.title.length > 5);

    return {
        title: 'ESA Newsroom — Press Releases',
        link: listUrl,
        item: items.map((x) => ({
            title: x.title,
            link: `https://www.esa.int${x.href}`,
            pubDate: x.date ? parseDate(Number.parseInt(x.date, 10) * 1000) : undefined,
        })),
    };
}
