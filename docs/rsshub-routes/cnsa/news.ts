import { load } from 'cheerio';
import type { Context } from 'hono';

import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';

export const route: Route = {
    path: '/news',
    categories: ['government'],
    example: '/cnsa/news',
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
            source: ['www.cnsa.gov.cn/english/n6465652/n6465653/index.html'],
            target: '/news',
        },
    ],
    name: 'News (English)',
    maintainers: ['8cli'],
    handler,
    url: 'http://www.cnsa.gov.cn/english/',
};

async function handler(): Promise<Data> {
    // CNSA 英文站新闻列表（Express Center → News）
    const listUrl = 'http://www.cnsa.gov.cn/english/n6465652/n6465653/index.html';
    const html = await ofetch(listUrl);
    const $ = load(html);

    const items = $('li.ej_cont_li > a')
        .toArray()
        .map((el) => {
            const $a = $(el);
            return {
                href: $a.attr('href')?.trim() ?? '',
                title: $a.text().trim(),
            };
        })
        .filter((x) => x.href.includes('/content.html') && x.title.length > 8);

    return {
        title: 'CNSA News (English)',
        link: listUrl,
        item: items.map((x) => ({
            title: x.title,
            link: new URL(x.href, listUrl).toString(),  // 相对列表页解析（../../ → /english/）
        })),
    };
}
