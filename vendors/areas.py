"""Delivery areas: the suburbs/estates/centres a vendor can tick, grouped, per county.

Hierarchy: county → group (a town or an area cluster) → the area a customer picks at checkout.
Plain data — no API, no migration. Add or edit a county below and it shows up immediately in
Dashboard → Delivery for vendors in that county. Duplicates are removed automatically
(case-insensitive, first group wins), so it is safe to paste overlapping lists.
"""

RAW = {
    # ── Nairobi metro ────────────────────────────────────────────────────
    "Nairobi": [
        ("Central & CBD", [
            "Nairobi CBD", "River Road", "Tom Mboya", "Haile Selassie", "Ngara", "Pangani", "Ziwani", "Kariokor",
            "Landimawe", "Pumwani", "Majengo", "Shauri Moyo", "Gikomba", "Industrial Area",
        ]),
        ("Westlands & Parklands", [
            "Westlands", "Parklands", "Highridge", "Kitisuru", "Karura", "Spring Valley", "Loresho", "Kangemi",
            "Mountain View", "Muthangari", "Riverside", "Brookside", "Gigiri", "Runda", "Nyari", "Rosslyn",
            "Thigiri", "Lower Kabete", "Muthaiga", "Muthaiga North", "Githogoro", "Kibagare", "Deep Sea",
            "Kiambu Road",
        ]),
        ("Kilimani, Lavington & Hurlingham", [
            "Kilimani", "Kileleshwa", "Lavington", "Lavington Green", "Hurlingham", "Adams Arcade", "Yaya",
            "Valley Arcade", "Woodley", "Hatheru", "Kabarnet Gardens", "Prestige",
        ]),
        ("Dagoretti & Ngong Road", [
            "Kawangware", "Dagoretti", "Dagoretti Corner", "Riruta", "Riruta Satellite", "Satellite", "Ngando",
            "Mutuini", "Gatina", "Kabiro", "Uthiru", "Ruthimitu", "Waithaka", "Kinoo",
        ]),
        ("Lang'ata & South", [
            "Karen", "Karen Shopping Centre", "Hardy", "Lang'ata", "Lang'ata South", "Nairobi West", "South B",
            "South C", "Nyayo Highrise", "Mugumo-ini", "Otiende", "Madaraka", "Wilson",
        ]),
        ("Kibra", [
            "Kibera", "Laini Saba", "Lindi", "Makina", "Sarang'ombe", "Olympic", "Olympic Estate", "Ayany",
            "Kenyatta Golf Course",
        ]),
        ("Kasarani & Roysambu", [
            "Kasarani", "Roysambu", "Roysambu Roundabout", "Zimmerman", "Githurai", "Kahawa", "Kahawa West",
            "Mwiki", "Clay City", "Njiru", "Ruai", "Kamulu", "Garden Estate", "Ridgeways", "Mirema", "Thome",
            "Seasons",
        ]),
        ("Ruaraka & north-east", [
            "Ruaraka", "Baba Dogo", "Utalii", "Mathare North", "Lucky Summer", "Korogocho", "Kariobangi",
            "Kariobangi North", "Kariobangi South", "Huruma", "Mlango Kubwa", "Mabatini", "Ngei", "Kiamaiko",
        ]),
        ("Eastlands", [
            "Eastleigh", "Eastleigh North", "Eastleigh South", "California", "Airbase", "Umoja", "Umoja I",
            "Umoja II", "Mowlem", "Donholm", "Tena", "Fedha", "Tassia", "Komarock", "Kayole", "Kayole North",
            "Kayole Central", "Kayole South", "Matopeni", "Dandora", "Dandora Phase 1", "Dandora Phase 2",
            "Dandora Phase 3", "Dandora Phase 4",
        ]),
        ("Embakasi & airport", [
            "Embakasi", "Upper Savanna", "Lower Savanna", "Utawala", "Mihango", "Imara Daima", "Pipeline",
            "Kware", "Kwa Njenga", "Kwa Reuben", "Mukuru", "Mukuru Kwa Njenga", "Mukuru Kwa Reuben",
            "Nyayo Estate", "Baraka", "Nyama Villa",
        ]),
        ("Makadara & Buruburu", [
            "Makadara", "Maringo", "Hamza", "Harambee", "Makongeni", "Viwandani", "Mbotela", "Bahati",
            "Jerusalem", "Buruburu", "Buruburu Phase 1", "Buruburu Phase 2", "Buruburu Phase 3",
            "Buruburu Phase 4", "Buruburu Phase 5",
        ]),
    ],
    "Kiambu": [
        ("Towns", [
            "Kiambu Town", "Thika", "Ruiru", "Limuru", "Kikuyu", "Karuri", "Githunguri", "Juja", "Lari",
            "Kabete", "Gatundu", "Gatundu South", "Wangige",
        ]),
        ("Ruaka & Kiambu Road", [
            "Ruaka", "Two Rivers", "Banana", "Ndenderu", "Muchatha", "Gachie", "Ting'ang'a",
        ]),
        ("Kikuyu & Limuru", [
            "Kinoo", "Zambezi", "Sigona", "Rungiri", "Muthiga", "Tigoni", "Ngecha", "Rironi", "Ndeiya",
        ]),
        ("Ruiru & Juja", [
            "Membley", "Kimbo", "Kahawa Sukari", "Kahawa Wendani", "Kwa Kairu", "Zetech", "Gatongora",
            "Kihunguro", "Matangi", "Murera", "Gitothua", "Kalimoni", "Theta", "Kenyatta Road", "Witeithie",
            "Mang'u", "Kamakis",
        ]),
        ("Thika", [
            "Section 9", "Section 6", "Landless", "Makongeni", "Ngoigwa", "Chania", "Chania Gardens", "Gretsa",
            "Garissa Road", "Blue Post",
        ]),
        ("Githunguri & north", ["Ikinu", "Komothai", "Githiga", "Kiamworia", "Kirigiti"]),
    ],
    "Kajiado": [
        ("Rongai & Ngong", [
            "Ongata Rongai", "Kiserian", "Ngong", "Matasia", "Kandisi", "Rimpa", "Nkoroi", "Olkeri", "Tuala",
            "Oloolua", "Kerarapon",
        ]),
        ("Kitengela & Isinya", ["Kitengela", "Milimani", "Acacia", "Noonkopir", "Isinya", "Kisaju", "Kaputiei"]),
        ("Other towns", [
            "Kajiado Town", "Namanga", "Kimana", "Bissil", "Mashuru", "Loitokitok", "Magadi", "Entasopia",
            "Ilbissil", "Rombo",
        ]),
    ],
    "Machakos": [
        ("Mavoko", ["Mlolongo", "Syokimau", "Athi River", "Katani", "Kinanie", "Mavoko", "Joska", "Malaa"]),
        ("Machakos town", ["Machakos Town", "Mjini", "Kariobangi", "Muthini", "Mumbuni", "Katoloni", "Miwani"]),
        ("Other towns", [
            "Tala", "Kangundo", "Matuu", "Masii", "Mwala", "Kathiani", "Wamunyu", "Kalama", "Mitaboni",
            "Kangonde", "Yatta",
        ]),
    ],
    # ── Coast ────────────────────────────────────────────────────────────
    "Mombasa": [
        ("Mombasa Island", [
            "Mombasa CBD", "Mombasa Island", "Mvita", "Old Town", "Kizingo", "Ganjoni", "Makadara", "Majengo",
            "Bondeni", "Tudor", "Tononoka", "Mama Ngina", "Digo Road", "Moi Avenue", "Makupa", "Buxton",
        ]),
        ("Nyali & Kisauni (north)", [
            "Nyali", "Nyali Estate", "Nyali Beach", "English Point", "Mkomani", "Frere Town", "Kongowea",
            "Ziwa la Ng'ombe", "Bombolulu", "Kadzandani", "Kisauni", "Mtopanga", "Mshomoroni", "Junda",
            "Bamburi", "Bamburi Mwisho", "Bamburi Beach", "Serena", "Shanzu", "Mtwapa", "Utange", "Magogoni",
            "Mwakirunge",
        ]),
        ("Changamwe & Jomvu (mainland)", [
            "Changamwe", "Jomvu", "Port Reitz", "Mikindani", "Magongo", "Kipevu", "Miritini", "Airport",
            "Kibarani", "Chaani",
        ]),
        ("Likoni (south)", ["Likoni", "Mtongwe", "Shelly Beach", "Timbwani", "Shika Adabu"]),
    ],
    "Kilifi": [
        ("Kilifi & Mnarani", [
            "Kilifi Town", "Mnarani", "Tezo", "Matsangoni", "Sokoni", "Kilifi Creek", "Takaungu", "Kuruwitu",
        ]),
        ("Mtwapa & Kikambala", ["Mtwapa", "Shimo la Tewa", "Majaoni", "Kikambala", "Vipingo", "Shanzu"]),
        ("Watamu & Gede", ["Watamu", "Jacaranda", "Blue Lagoon", "Gede", "Dabaso", "Uyombo", "Mida"]),
        ("Malindi & Magarini", [
            "Malindi", "Shella", "Casuarina", "Mayungu", "Mambrui", "Marafa", "Gongoni", "Magarini", "Garashi",
        ]),
        ("Inland", [
            "Mariakani", "Mazeras", "Rabai", "Ribe", "Jibana", "Kambe", "Kaloleni", "Ganze", "Bamba",
            "Vitengeni",
        ]),
    ],
    "Kwale": [
        ("Diani & south coast", [
            "Diani", "Ukunda", "Galu", "Tiwi", "Msambweni", "Kinondo", "Gazi", "Shimoni", "Vanga",
            "Lunga Lunga",
        ]),
        ("Inland", ["Kwale Town", "Shimba Hills", "Kubo", "Mackinnon Road", "Samburu", "Taru", "Kinango"]),
    ],
    "Taita-Taveta": [
        ("Voi & Mwatate", ["Voi", "Mwatate", "Maungu", "Manyani", "Sagalla", "Mbololo", "Bura"]),
        ("Wundanyi & Taveta", ["Wundanyi", "Werugha", "Mgange", "Taveta", "Mahoo", "Challa", "Mata"]),
    ],
    "Tana River": [
        ("Towns & centres", [
            "Hola", "Garsen", "Bura", "Madogo", "Kipini", "Wenje", "Tarasaa", "Minjila", "Chewani", "Waldena",
        ]),
    ],
    "Lamu": [
        ("Lamu & islands", ["Lamu Town", "Amu", "Shela", "Matondoni", "Manda", "Faza", "Kizingitini", "Pate"]),
        ("Mainland", ["Mokowe", "Hindi", "Mpeketoni", "Witu", "Kiunga", "Bahari", "Basuba"]),
    ],
    # ── Rift Valley ──────────────────────────────────────────────────────
    "Nakuru": [
        ("Nakuru town — estates & suburbs", [
            "Nakuru CBD", "Milimani", "Section 58", "Naka", "Lanet", "Kiamunyi", "Rhonda", "Kaptembwa",
            "Mwariki", "Shabab", "Free Area", "London", "Pipeline", "Flamingo", "Kaloleni", "Kivumbini",
            "Bondeni", "Biashara", "Ngala", "Kenlands", "Teachers", "Workers", "White House", "Langa Langa",
            "Majengo", "Baharini", "Lumumba", "Dedan Kimathi", "Lower Misonge", "Moi Flats", "Shauri Yako",
            "Ojuka", "Paul Machanga", "Upper Menengai", "Menengai", "Mawanga", "Kabachia", "Tegat",
            "Industrial Area", "Viwanda", "Engashura", "Kiamunyeki",
        ]),
        ("Naivasha", [
            "Naivasha Town", "Lakeview", "Karagita", "Hell's Gate", "Naivasha East", "Viwandani", "Kabati",
            "Mai Mahiu", "Kinungi", "Kongoni", "Olkaria", "Maiella", "Mbaruk", "Eburu", "Gilgil Road",
        ]),
        ("Gilgil & Elementaita", ["Gilgil", "Elementaita", "Malewa", "Murindati", "Kikopey"]),
        ("Njoro, Molo & Kuresoi", [
            "Njoro", "Egerton", "Lare", "Nessuit", "Kihingo", "Mauche", "Mau Narok", "Molo", "Turi",
            "Mariashoni", "Elburgon", "Kuresoi", "Kiptagich", "Tinet", "Keringet", "Olenguruone",
        ]),
        ("Rongai & Solai", ["Rongai", "Salgaa", "Solai", "Menengai West", "Soin", "Visoi", "Mosop"]),
        ("Bahati & Subukia", [
            "Bahati", "Dundori", "Kiamaina", "Kabatini", "Umoja", "Subukia", "Waseges", "Kabazi",
        ]),
    ],
    "Baringo": [
        ("Towns & centres", [
            "Kabarnet", "Eldama Ravine", "Marigat", "Mogotio", "Kabartonjo", "Barwessa", "Chemolingot",
            "Loruk", "Tangulbei", "Kolowa", "Bartabwa", "Sacho", "Tenges", "Kipsaraman", "Torongo", "Emining",
            "Kisanana", "Salawa",
        ]),
    ],
    "Bomet": [
        ("Bomet & Longisa", ["Bomet Town", "Silibwet", "Longisa", "Merigi", "Kembu", "Tenwek", "Chesoen"]),
        ("Sotik & Chepalungu", [
            "Sotik", "Kaplong", "Mulot", "Ndanai", "Chebole", "Mogogosiek", "Sigor", "Chebunyo", "Olbutyo",
            "Kipreres",
        ]),
    ],
    "Elgeyo-Marakwet": [
        ("Towns & centres", [
            "Iten", "Tambach", "Kapsowar", "Chebiemit", "Kapcherop", "Chepkorio", "Kaptarakwa", "Flax",
            "Kessup", "Nyaru", "Kapyego", "Chesoi", "Kapteren",
        ]),
    ],
    "Kericho": [
        ("Kericho town", [
            "Kericho Town", "Majengo", "Kapsoit", "Kapsuser", "Sosiot", "Brooke", "Kipchebor", "Ainamoi",
            "Kabianga", "Chepseon",
        ]),
        ("Other towns", ["Litein", "Kipkelion", "Londiani", "Fort Ternan", "Roret", "Sigowet", "Sosiot", "Kunyak"]),
    ],
    "Laikipia": [
        ("Nanyuki", ["Nanyuki Town", "Majengo", "Likii", "Nturukuma", "Kalalu", "Jua Kali", "Marura"]),
        ("Nyahururu & Rumuruti", [
            "Nyahururu", "Rumuruti", "Igwamiti", "Marmanet", "Sipili", "Kinamba", "Ol Moran", "Wiyumiririe",
            "Doldol", "Sosian",
        ]),
    ],
    "Nandi": [
        ("Towns & centres", [
            "Kapsabet", "Nandi Hills", "Mosoriot", "Kabiyet", "Kaiboi", "Kobujoi", "Chepterit", "Lessos",
            "Kipkaren", "Meteitei", "Kilibwoni", "Tinderet", "Kaptumo", "Serem",
        ]),
    ],
    "Narok": [
        ("Narok town", ["Narok Town", "Majengo", "Ololulung'a", "Ewaso Ng'iro", "Nairagie Enkare", "Suswa"]),
        ("Maasai Mara & west", [
            "Sekenani", "Talek", "Naikarra", "Aitong", "Kilgoris", "Lolgorian", "Ngorengore", "Emurua Dikirr",
            "Mulot", "Sogoo",
        ]),
    ],
    "Nyandarua": [
        ("Towns & centres", [
            "Ol Kalou", "Njabini", "Engineer", "Ndaragwa", "Kinangop", "Magumu", "Mairo Inya", "Wanjohi",
            "Kipipiri", "Geta", "Miharati", "Kasuku", "Shamata",
        ]),
    ],
    "Samburu": [
        ("Towns & centres", [
            "Maralal", "Baragoi", "Wamba", "Suguta Marmar", "Lodokejek", "Kisima", "South Horr", "Barsaloi",
            "Loosuk", "Nachola", "Archer's Post",
        ]),
    ],
    "Trans Nzoia": [
        ("Kitale town", [
            "Kitale Town", "Milimani", "Matisi", "Mitume", "Tuwan", "Kipsongo", "Shauri Yako", "Bondeni",
            "Section 6", "Kolongolo",
        ]),
        ("Other towns", [
            "Kiminini", "Endebess", "Kwanza", "Saboti", "Mois Bridge", "Sikhendu", "Namanjalala",
            "Chepchoina", "Bikeke", "Matunda",
        ]),
    ],
    "Turkana": [
        ("Towns & centres", [
            "Lodwar", "Kakuma", "Lokichar", "Lokichogio", "Kalokol", "Kainuk", "Lokori", "Lorugum", "Katilu",
            "Turkwel", "Kibish", "Napeitom", "Loima", "Kerio",
        ]),
    ],
    "Uasin Gishu": [
        ("Eldoret town", [
            "Eldoret CBD", "Elgon View", "Kapsoya", "Langas", "Huruma", "Pioneer", "Annex", "West Indies",
            "Kahoya", "Munyaka", "Kimumu", "Yamumbi", "Mwanzo", "Shauri", "Racecourse", "Hill School",
            "Kamukunji", "Kipkorgot", "Testimony", "Sosiani", "Maili Nne", "Chepkoilel",
        ]),
        ("Other towns", ["Burnt Forest", "Moi University", "Kesses", "Ziwa", "Turbo", "Kipkaren", "Timboroa", "Moiben"]),
    ],
    "West Pokot": [
        ("Towns & centres", [
            "Kapenguria", "Makutano", "Chepareria", "Kacheliba", "Sigor", "Ortum", "Lomut", "Alale",
            "Kabichbich", "Sook", "Konyao", "Chesegon",
        ]),
    ],
    # ── Nyanza ───────────────────────────────────────────────────────────
    "Kisumu": [
        ("Kisumu city — estates & suburbs", [
            "Kisumu CBD", "Milimani", "Nyalenda A", "Nyalenda B", "Manyatta A", "Manyatta B", "Kondele",
            "Migosi", "Mamboleo", "Kanyakwar", "Lolwe", "Kibuye", "Obunga", "Bandani", "Nyamasaria", "Kibos",
            "Pandpieri", "Railways", "Kaloleni", "Shauri Moyo", "Arina", "Okore", "Robert Ouko", "Tom Mboya",
            "Mountain View", "Polyview", "Pembe Tatu", "Lumumba", "Ondiek", "Argwings Kodhek", "Mosque",
            "Kenya Re", "Airport View", "Afya Estate", "Nyawita", "Riat Hills", "Kajulu", "Dunga", "Otonglo",
            "Kisian", "Ojola", "Korando",
        ]),
        ("Towns & urban centres", [
            "Ahero", "Maseno", "Muhoroni", "Awasi", "Chemelil", "Koru", "Miwani", "Katito", "Kombewa",
            "Sondu", "Masogo", "Ombeyi",
        ]),
        ("Wider county", [
            "Onjiko", "Nyang'oma", "Pap Onditi", "Akala", "Nyakach", "Seme", "Kolwa", "Kabonyo", "Kanyagwal",
        ]),
    ],
    "Homa Bay": [
        ("Homa Bay town", ["Homa Bay Town", "Shauri Yako", "Sofia", "Arujo", "Makongeni", "Sikri"]),
        ("Other towns", [
            "Oyugis", "Kendu Bay", "Rodi Kopany", "Ndhiwa", "Rangwe", "Mbita", "Sindo", "Kadongo", "Magunga",
            "Nyandiwa", "Mfangano", "Kosele", "Marindi",
        ]),
    ],
    "Migori": [
        ("Migori town", ["Migori Town", "Oruba", "Nyabisawa", "Suna", "Mabera"]),
        ("Other towns", [
            "Rongo", "Awendo", "Isebania", "Kehancha", "Muhuru Bay", "Sori", "Karungu", "Uriri", "Ranen",
            "Macalder", "Nyatike", "Ntimaru", "Masara",
        ]),
    ],
    "Kisii": [
        ("Kisii town", [
            "Kisii Town", "Nyanchwa", "Daraja Mbili", "Mwembe", "Nyamataro", "Jogoo", "Milimani", "Gekomu",
            "Menyinkwa", "Nubia",
        ]),
        ("Other towns", [
            "Suneka", "Ogembo", "Keroka", "Nyamache", "Marani", "Masimba", "Kenyenya", "Nyamarambe", "Etago",
            "Tabaka", "Itibo", "Rioma",
        ]),
    ],
    "Nyamira": [
        ("Towns & centres", [
            "Nyamira Town", "Keroka", "Nyansiongo", "Ekerenyo", "Manga", "Miruka", "Ikonge", "Esise",
            "Kebirigo", "Magwagwa", "Gesima", "Kemera",
        ]),
    ],
    "Siaya": [
        ("Towns & centres", [
            "Siaya Town", "Bondo", "Yala", "Ugunja", "Ukwala", "Usenge", "Akala", "Madiany", "Ndori", "Sega",
            "Nyangoma", "Boro", "Wagai", "Sidindi", "Rarieda", "Luanda K'otieno",
        ]),
    ],
    # ── Western ──────────────────────────────────────────────────────────
    "Kakamega": [
        ("Kakamega town", [
            "Kakamega Town", "Amalemba", "Milimani", "Shirere", "Mudiri", "Bukhungu", "Sichirai", "Maraba",
            "Lurambi", "Muslim", "Nabongo",
        ]),
        ("Other towns", [
            "Mumias", "Butere", "Khwisero", "Malava", "Lugari", "Matunda", "Shianda", "Musanda", "Ekero",
            "Shinyalu", "Ileho", "Kambiri", "Navakholo", "Sabatia Junction",
        ]),
    ],
    "Bungoma": [
        ("Bungoma town", [
            "Bungoma Town", "Kanduyi", "Musikoma", "Sang'alo", "Mateka", "Milimani", "Khalaba", "Township",
            "Bukembe",
        ]),
        ("Other towns", [
            "Webuye", "Kimilili", "Chwele", "Sirisia", "Malakisi", "Bumula", "Naitiri", "Ndalu", "Kabuchai",
            "Cheptais", "Kapsokwony", "Lwakhakha", "Myanga", "Misikhu",
        ]),
    ],
    "Busia": [
        ("Towns & centres", [
            "Busia Town", "Mundika", "Nambale", "Matayos", "Butula", "Bumala", "Funyula", "Port Victoria",
            "Malaba", "Sio Port", "Budalangi", "Amukura", "Angurai", "Adungosi",
        ]),
    ],
    "Vihiga": [
        ("Towns & centres", [
            "Mbale", "Chavakali", "Luanda", "Majengo", "Emuhaya", "Serem", "Hamisi", "Shamakhokho", "Ekwanda",
            "Mudete", "Cheptulu", "Esiandumba",
        ]),
    ],
    # ── Central & Eastern ────────────────────────────────────────────────
    "Nyeri": [
        ("Nyeri town", ["Nyeri Town", "Kamakwa", "Ruring'u", "Majengo", "Kingongo", "Blue Valley", "Kiganjo"]),
        ("Other towns", ["Karatina", "Chaka", "Othaya", "Mweiga", "Naro Moru", "Mukurweini", "Endarasha", "Kiganjo"]),
    ],
    "Murang'a": [
        ("Murang'a town", ["Murang'a Town", "Mukuyu", "Sabasaba", "Kiharu", "Kahuro"]),
        ("Other towns", [
            "Kenol", "Maragua", "Makuyu", "Kandara", "Gatanga", "Githumu", "Kangema", "Kiriaini", "Kangari",
            "Kigumo", "Ithanga", "Kabati",
        ]),
    ],
    "Kirinyaga": [
        ("Towns & centres", [
            "Kerugoya", "Kutus", "Sagana", "Kagio", "Wanguru", "Ngurubani", "Baricho", "Kianyaga", "Kimbimbi",
            "Difathas", "Kagumo", "Mutithi", "Kandongu",
        ]),
    ],
    "Embu": [
        ("Embu town", [
            "Embu Town", "Majimbo", "Blue Valley", "Dallas", "Kangaru", "Kirimari", "Njukiri", "Stadium",
            "Kamiu",
        ]),
        ("Other towns", ["Runyenjes", "Manyatta", "Kibugu", "Karurumo", "Siakago", "Ishiara", "Kiritiri", "Mbeere"]),
    ],
    "Tharaka-Nithi": [
        ("Towns & centres", [
            "Chuka", "Chogoria", "Kathwana", "Marimanti", "Gatunga", "Mukothima", "Magumoni", "Karingani",
            "Mwimbi", "Ganga",
        ]),
    ],
    "Meru": [
        ("Meru town", ["Meru Town", "Makutano", "Gakoromone", "Kaaga", "Milimani", "Mwendantu", "Gitoro"]),
        ("Other towns", [
            "Nkubu", "Timau", "Maua", "Mikinduri", "Kibirichia", "Githongo", "Kanyakine", "Muriri",
            "Laare", "Mutuati", "Kianjai", "Mitunguu",
        ]),
    ],
    "Kitui": [
        ("Kitui town", ["Kitui Town", "Kalundu", "Manyenyoni", "Mulango", "Kunda Kindu", "Township"]),
        ("Other towns", [
            "Mwingi", "Mutomo", "Kabati", "Migwani", "Nuu", "Ikutha", "Mutitu", "Zombe", "Kyuso", "Tseikuru",
            "Katse", "Endau", "Matinyani", "Kauwi", "Chuluni",
        ]),
    ],
    "Makueni": [
        ("Towns & centres", [
            "Wote", "Emali", "Sultan Hamud", "Kibwezi", "Mtito Andei", "Makindu", "Tawa", "Kalawa",
            "Kathonzweni", "Mbumbuni", "Nunguni", "Kilungu", "Matiliku", "Kasikeu", "Kikima",
        ]),
    ],
    # ── North & North Eastern ────────────────────────────────────────────
    "Isiolo": [
        ("Towns & centres", [
            "Isiolo Town", "Bulla Pesa", "Kiwanjani", "Wabera", "Ngaremara", "Archer's Post", "Merti",
            "Garbatulla", "Kinna", "Oldonyiro", "Kipsing", "Sericho",
        ]),
    ],
    "Marsabit": [
        ("Towns & centres", [
            "Marsabit Town", "Moyale", "Sololo", "Laisamis", "Merille", "Loiyangalani", "North Horr",
            "Maikona", "Turbi", "Kargi", "Illeret", "Dukana", "Bubisa", "Karare", "Songa",
        ]),
    ],
    "Garissa": [
        ("Garissa town", ["Garissa Town", "Township", "Bulla Iftin", "Bulla Punda", "Sankuri", "Iftin"]),
        ("Other towns", [
            "Balambala", "Bura", "Modogashe", "Dadaab", "Masalani", "Ijara", "Hulugho", "Liboi", "Fafi",
            "Shantabak",
        ]),
    ],
    "Wajir": [
        ("Towns & centres", [
            "Wajir Town", "Township", "Habaswein", "Griftu", "Bute", "Tarbaj", "Eldas", "Khorof Harar",
            "Buna", "Diff", "Sabuli", "Wagalla",
        ]),
    ],
    "Mandera": [
        ("Towns & centres", [
            "Mandera Town", "Township", "Elwak", "Rhamu", "Takaba", "Banissa", "Lafey", "Fino", "Kutulo",
            "Arabia", "Ashabito", "Khalalio",
        ]),
    ],
}


def _dedupe(groups):
    """Drop repeats within a county (first group wins) and empty groups."""
    seen, out = set(), []
    for label, names in groups:
        keep = []
        for n in names:
            k = n.strip().lower()
            if n.strip() and k not in seen:
                seen.add(k)
                keep.append(n.strip())
        if keep:
            out.append((label, keep))
    return out


AREA_GROUPS = {county: _dedupe(groups) for county, groups in RAW.items()}
AREAS = {county: [n for _, names in groups for n in names] for county, groups in AREA_GROUPS.items()}


def groups_for(county):
    """[(group label, [area…])] for this county — empty when we don't have a list yet."""
    return AREA_GROUPS.get((county or "").strip(), [])


def areas_for(county):
    """Flat list of every suggested area in this county."""
    return AREAS.get((county or "").strip(), [])
