// E-book page manifest.
// type: "cover" | "content" | "author" | "last"
// Content pages use video (seamless loop) + narration audio + text.
// Cover / author / last pages are static (no narration, no video).
window.EBOOK = {
  title: "The Three Little Pigs",
  pages: [
    {
      type: "cover",
      heading: "The Three Little Pigs",
      sub: "An animated audio picture book",
      hint: "Tap Start to begin"
    },
    {
      type: "content",
      id: "page1",
      text: "Splash! And that was the end of the big, bad wolf.",
      video: "assets/page1.mp4",
      poster: "assets/page1_frame.jpg",
      audio: "assets/page1_narration.mp3",
      // Where the printed text sits on the page (normalized 0-1000 coords from OCR grounding).
      // The original glyphs were removed from the image; we re-type them here in place.
      layout: {
        lines: [
          { text: "Splash!", box: [102, 130, 214, 178] },
          { text: "And that was the end of", box: [102, 189, 453, 232] },
          { text: "the big, bad wolf.", box: [102, 246, 351, 289] }
        ],
        // Page numbers were erased from the source (so the video can't garble them)
        // and are re-drawn here as crisp static overlays.
        pageNumbers: [
          { text: "26", box: [65, 894, 93, 924] },
          { text: "27", box: [926, 901, 954, 931] }
        ]
      }
    },
    {
      type: "author",
      heading: "About the Author",
      body: "Retold for little readers. Illustrations and animation generated with AI."
    },
    {
      type: "last",
      heading: "The End",
      body: "Well done, reader! You finished the story."
    }
  ]
};
