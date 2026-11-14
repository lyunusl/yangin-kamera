"""Kural sınamalarının sonucu. Bu dosyayı egitim/dene_kurallar.py yazar; elle değiştirmeyin.

yakalanan/beklenen: durumun bulunduğu yapay tespit dizilerinden kaçında olay başladı · yanlis/denetim: durumun
bulunmadığı dizilerden kaçında yanlış olay başladı. Tespitler elle üretilmiştir; model bu sınamada çalışmaz.
"""
SINAMA = {
    "alev": {"yakalanan": 9, "beklenen": 9, "yanlis": 0, "denetim": 9},
    "alev_duman": {"yakalanan": 1, "beklenen": 1, "yanlis": 0, "denetim": 7},
    "alev_buyuyor": {"yakalanan": 1, "beklenen": 1, "yanlis": 0, "denetim": 9},
    "duman": {"yakalanan": 5, "beklenen": 5, "yanlis": 0, "denetim": 7},
    "duman_yayiliyor": {"yakalanan": 1, "beklenen": 1, "yanlis": 0, "denetim": 7},
    "kritik_bolge": {"yakalanan": 2, "beklenen": 2, "yanlis": 0, "denetim": 2},
}
