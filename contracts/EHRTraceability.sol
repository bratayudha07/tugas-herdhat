pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";

contract EHRTraceability is ERC721URIStorage {

    // ==========================================
    // STATUS REKAM MEDIS
    // ==========================================

    enum Status {
        CREATED,
        EXAMINED,
        DIAGNOSED,
        TREATED,
        COMPLETED
    }

    // ==========================================
    // DATA BATCH PASIEN
    // ==========================================

    struct PatientBatch {
        uint256 tokenId;
        string patientId;
        string patientName;
        string complaint;   // keluhan
        string treatment;   // tindakan
        string medicine;    // obat
        Status status;
        uint256 createdAt;
    }

    struct History {
        string action;
        address actor;
        uint256 timestamp;
    }

    // ==========================================
    // VARIABLE
    // ==========================================

    uint256 private nextTokenId = 1;

    mapping(uint256 => PatientBatch) public batches;

    mapping(uint256 => History[]) private histories;

    // ==========================================
    // EVENT
    // ==========================================

    event BatchCreated(uint256 indexed tokenId, address indexed owner, string patientName);
    event StatusUpdated(uint256 indexed tokenId, Status oldStatus, Status newStatus);

    // ==========================================
    // CONSTRUCTOR
    // ==========================================

    constructor()
        ERC721("EHR Traceability", "EHR")
    {}

    // ==========================================
    // 1. MINT NFT
    // ==========================================

    function mint(
        address to,
        uint256 tokenId,
        string memory metadataURI
    )
        internal
    {
        // Membuat NFT
        _safeMint(to, tokenId);

        // Menyimpan metadata NFT
        _setTokenURI(tokenId, metadataURI);
    }

    // ==========================================
    // 2. MEMBUAT BATCH PASIEN (flowchart: Create batch)
    // ==========================================

    function createBatch(
        string memory patientId,
        string memory patientName,
        string memory complaint,
        address patient,
        string memory metadataURI
    )
        public
        returns (uint256)
    {
        // Validasi: data tidak boleh kosong
        require(bytes(patientId).length > 0, "ID pasien wajib diisi");
        require(bytes(patientName).length > 0, "Nama pasien wajib diisi");
        require(bytes(complaint).length > 0, "Keluhan wajib diisi");
        require(patient != address(0), "Alamat pasien tidak valid");

        // ======================================
        // AMBIL TOKEN ID
        // ======================================
        uint256 tokenId = nextTokenId;

        // ======================================
        // MINT NFT (pemilik = pasien)
        // ======================================
        mint(patient, tokenId, metadataURI);

        // ======================================
        // TOKEN ID BERIKUTNYA
        // ======================================
        nextTokenId++;

        // ======================================
        // SIMPAN DATA BATCH
        // ======================================
        batches[tokenId] = PatientBatch({
            tokenId: tokenId,
            patientId: patientId,
            patientName: patientName,
            complaint: complaint,
            treatment: "",
            medicine: "",
            status: Status.CREATED,
            createdAt: block.timestamp
        });

        // ======================================
        // SIMPAN HISTORY
        // ======================================
        histories[tokenId].push(
            History({
                action: "BATCH_CREATED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        // ======================================
        // EVENT
        // ======================================
        emit BatchCreated(tokenId, patient, patientName);

        return tokenId;
    }

    // ==========================================
    // 3. UPDATE STATUS (flowchart: Update status)
    // ==========================================

    function updateStatus(
        uint256 tokenId,
        Status newStatus
    )
        public
    {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");

        require(ownerOf(tokenId) == msg.sender, "Bukan pemilik batch");

        // Status sesuai aturan? (hanya boleh maju satu tahap)
        Status oldStatus = batches[tokenId].status;
        require(
            uint8(newStatus) == uint8(oldStatus) + 1,
            "Status tidak valid"
        );

        // Ubah status dan simpan
        batches[tokenId].status = newStatus;

        // Catat riwayat
        histories[tokenId].push(
            History({
                action: "STATUS_UPDATED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit StatusUpdated(tokenId, oldStatus, newStatus);
    }

    // ==========================================
    // 4. ISI TINDAKAN & OBAT (melengkapi data Get batch)
    // ==========================================

    function updateTreatment(
        uint256 tokenId,
        string memory treatment,
        string memory medicine
    )
        public
    {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");
        require(ownerOf(tokenId) == msg.sender, "Bukan pemilik batch");

        batches[tokenId].treatment = treatment;
        batches[tokenId].medicine = medicine;

        histories[tokenId].push(
            History({
                action: "TREATMENT_UPDATED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );
    }

    // ==========================================
    // 5. MELIHAT DATA BATCH (flowchart: Get batch)
    // ==========================================

    function getBatch(
        uint256 tokenId
    )
        public
        view
        returns (PatientBatch memory)
    {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");

        return batches[tokenId];
    }

    // ==========================================
    // 6. MELIHAT RIWAYAT (flowchart: Get history)
    // ==========================================

    function getHistory(
        uint256 tokenId
    )
        public
        view
        returns (History[] memory)
    {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");

        History[] storage source = histories[tokenId];
        History[] memory result = new History[](source.length);

        for (uint256 i = 0; i < source.length; i++) {
            result[i] = source[source.length - 1 - i];
        }

        return result;
    }

    // ==========================================
    // 7. CEK PEMILIK NFT
    // ==========================================

    function getOwner(
        uint256 tokenId
    )
        public
        view
        returns (address)
    {
        return ownerOf(tokenId);
    }

    function getBatchOwner(
        uint256 tokenId
    )
        public
        view
        returns (address)
    {
        require(
            _ownerOf(tokenId) != address(0),
            "NFT tidak ditemukan"
        );

        return ownerOf(tokenId);
    }
}
