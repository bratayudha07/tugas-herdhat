// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";

contract EHRTraceability is ERC721URIStorage {

    // ==========================================
    // TIPE DATA
    // ==========================================

    enum Status {
        CREATED,
        EXAMINED,
        DIAGNOSED,
        TREATED,
        COMPLETED
    }

    enum Role {
        NONE,
        RECEPTIONIST,
        DOCTOR,
        ADMIN
    }

    struct PatientBatch {
        uint256 tokenId;
        string patientId;
        string patientName;
        string complaint;
        string treatment;
        string medicine;
        Status status;
        uint256 createdAt;
        // field baru (append-only, index 0-7 tetap sama)
        address createdBy;
        address doctor;
        address patient;
    }

    struct History {
        string action;
        address actor;
        uint256 timestamp;
    }

    // ==========================================
    // STATE
    // ==========================================

    uint256 private nextTokenId = 1;

    mapping(address => Role) public roles;

    mapping(uint256 => PatientBatch) public batches;

    mapping(uint256 => History[]) private histories;

    mapping(uint256 => mapping(address => bool)) public consent;

    // Daftar dokter terdaftar, supaya UI bisa menampilkan pilihan dokter
    // tanpa perlu membaca event.
    address[] private doctorList;

    // 1-based index ke doctorList; 0 berarti bukan dokter.
    mapping(address => uint256) private doctorIndex;

    // ==========================================
    // EVENT
    // ==========================================

    event BatchCreated(
        uint256 indexed tokenId,
        address indexed patient,
        string patientName
    );

    event StatusUpdated(
        uint256 indexed tokenId,
        Status oldStatus,
        Status newStatus
    );

    event TreatmentUpdated(
        uint256 indexed tokenId,
        string oldTreatment,
        string oldMedicine,
        string newTreatment,
        string newMedicine
    );

    event DoctorAssigned(
        uint256 indexed tokenId,
        address indexed doctor
    );

    event ConsentChanged(
        uint256 indexed tokenId,
        address indexed doctor,
        bool granted
    );

    event RoleChanged(
        address indexed account,
        Role oldRole,
        Role newRole
    );

    // ==========================================
    // MODIFIER
    // ==========================================

    modifier onlyAdmin() {
        require(roles[msg.sender] == Role.ADMIN, "Hanya admin");
        _;
    }

    modifier onlyReceptionist() {
        require(roles[msg.sender] == Role.RECEPTIONIST, "Hanya resepsionis");
        _;
    }

    modifier batchExists(uint256 tokenId) {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");
        _;
    }

    modifier onlyDoctorFor(uint256 tokenId) {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");
        require(roles[msg.sender] == Role.DOCTOR, "Bukan dokter");
        require(
            batches[tokenId].doctor == msg.sender,
            "Bukan dokter penanggung jawab"
        );
        require(consent[tokenId][msg.sender], "Pasien belum memberi izin");
        _;
    }

    modifier onlyPatientFor(uint256 tokenId) {
        require(_ownerOf(tokenId) != address(0), "Batch tidak ditemukan");
        require(
            ownerOf(tokenId) == msg.sender,
            "Hanya pasien pemilik rekam medis"
        );
        _;
    }

    // ==========================================
    // CONSTRUCTOR
    // ==========================================

    constructor() ERC721("EHR Traceability", "EHR") {
        roles[msg.sender] = Role.ADMIN;
    }

    // ==========================================
    // MANAJEMEN PERAN (admin)
    // ==========================================

    function setRole(address account, Role role) public onlyAdmin {
        require(account != address(0), "Alamat tidak valid");
        require(
            account != msg.sender,
            "Admin tidak dapat mengubah perannya sendiri"
        );

        Role oldRole = roles[account];

        roles[account] = role;

        if (role == Role.DOCTOR) {
            if (doctorIndex[account] == 0) {
                doctorList.push(account);
                doctorIndex[account] = doctorList.length;
            }
        } else {
            _removeDoctor(account);
        }

        emit RoleChanged(account, oldRole, role);
    }

    function getRole(address account) public view returns (Role) {
        return roles[account];
    }

    function getDoctors() public view returns (address[] memory) {
        return doctorList;
    }

    function _removeDoctor(address account) internal {
        uint256 index = doctorIndex[account];

        if (index == 0) {
            return;
        }

        uint256 lastIndex = doctorList.length - 1;
        uint256 position = index - 1;

        if (position != lastIndex) {
            address moved = doctorList[lastIndex];
            doctorList[position] = moved;
            doctorIndex[moved] = index;
        }

        doctorList.pop();
        doctorIndex[account] = 0;
    }

    // ==========================================
    // 1. MINT NFT
    // ==========================================

    function _mintBatch(
        address to,
        uint256 tokenId,
        string memory metadataURI
    )
        internal
    {
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, metadataURI);
    }

    // ==========================================
    // 2. BUAT BATCH (resepsionis)
    // ==========================================

    function createBatch(
        string memory patientId,
        string memory patientName,
        string memory complaint,
        address patient,
        address doctor,
        string memory metadataURI
    )
        public
        onlyReceptionist
        returns (uint256)
    {
        require(bytes(patientId).length > 0, "ID pasien wajib diisi");
        require(bytes(patientName).length > 0, "Nama pasien wajib diisi");
        require(bytes(complaint).length > 0, "Keluhan wajib diisi");
        require(patient != address(0), "Alamat pasien tidak valid");
        require(roles[doctor] == Role.DOCTOR, "Alamat dokter tidak terdaftar");

        uint256 tokenId = nextTokenId;

        _mintBatch(patient, tokenId, metadataURI);

        nextTokenId++;

        batches[tokenId] = PatientBatch({
            tokenId: tokenId,
            patientId: patientId,
            patientName: patientName,
            complaint: complaint,
            treatment: "",
            medicine: "",
            status: Status.CREATED,
            createdAt: block.timestamp,
            createdBy: msg.sender,
            doctor: doctor,
            patient: patient
        });

        histories[tokenId].push(
            History({
                action: "BATCH_CREATED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit BatchCreated(tokenId, patient, patientName);

        return tokenId;
    }

    // ==========================================
    // 3. TUNJUK DOKTER (resepsionis)
    // ==========================================

    function assignDoctor(
        uint256 tokenId,
        address doctor
    )
        public
        onlyReceptionist
        batchExists(tokenId)
    {
        require(roles[doctor] == Role.DOCTOR, "Alamat dokter tidak terdaftar");
        require(
            batches[tokenId].status != Status.COMPLETED,
            "Rekam medis sudah selesai"
        );

        address oldDoctor = batches[tokenId].doctor;

        // Izin dokter lama dicabut supaya tidak ikut terbawa.
        if (oldDoctor != address(0)) {
            consent[tokenId][oldDoctor] = false;
        }

        batches[tokenId].doctor = doctor;

        histories[tokenId].push(
            History({
                action: "DOCTOR_ASSIGNED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit DoctorAssigned(tokenId, doctor);
    }

    // ==========================================
    // 4. PERSETUJUAN PASIEN
    // ==========================================

    function setConsent(
        uint256 tokenId,
        bool granted
    )
        public
        onlyPatientFor(tokenId)
    {
        address doctor = batches[tokenId].doctor;

        require(doctor != address(0), "Dokter penanggung jawab belum ditetapkan");
        require(
            batches[tokenId].status != Status.COMPLETED,
            "Rekam medis sudah selesai"
        );

        consent[tokenId][doctor] = granted;

        histories[tokenId].push(
            History({
                action: granted ? "CONSENT_GRANTED" : "CONSENT_REVOKED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit ConsentChanged(tokenId, doctor, granted);
    }

    // ==========================================
    // 5. UPDATE STATUS (dokter penanggung jawab)
    // ==========================================

    function updateStatus(
        uint256 tokenId,
        Status newStatus
    )
        public
        onlyDoctorFor(tokenId)
    {
        Status oldStatus = batches[tokenId].status;

        require(oldStatus != Status.COMPLETED, "Rekam medis sudah selesai");
        require(
            uint8(newStatus) == uint8(oldStatus) + 1,
            "Status tidak valid"
        );

        batches[tokenId].status = newStatus;

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
    // 6. TINDAKAN & OBAT (dokter penanggung jawab)
    // ==========================================

    function updateTreatment(
        uint256 tokenId,
        string memory treatment,
        string memory medicine
    )
        public
        onlyDoctorFor(tokenId)
    {
        require(
            batches[tokenId].status != Status.COMPLETED,
            "Rekam medis sudah selesai"
        );
        require(
            bytes(treatment).length > 0 || bytes(medicine).length > 0,
            "Isi tindakan atau obat"
        );

        PatientBatch storage batch = batches[tokenId];

        string memory oldTreatment = batch.treatment;
        string memory oldMedicine = batch.medicine;

        batch.treatment = treatment;
        batch.medicine = medicine;

        histories[tokenId].push(
            History({
                action: "TREATMENT_UPDATED",
                actor: msg.sender,
                timestamp: block.timestamp
            })
        );

        emit TreatmentUpdated(
            tokenId,
            oldTreatment,
            oldMedicine,
            treatment,
            medicine
        );
    }

    // ==========================================
    // 7. BACA DATA
    // ==========================================

    function getBatch(
        uint256 tokenId
    )
        public
        view
        batchExists(tokenId)
        returns (PatientBatch memory)
    {
        return batches[tokenId];
    }

    function getHistory(
        uint256 tokenId
    )
        public
        view
        batchExists(tokenId)
        returns (History[] memory)
    {
        History[] storage source = histories[tokenId];

        History[] memory result = new History[](source.length);

        for (uint256 i = 0; i < source.length; i++) {
            result[i] = source[source.length - 1 - i];
        }

        return result;
    }

    function totalSupply() public view returns (uint256) {
        return nextTokenId - 1;
    }

    function getOwner(uint256 tokenId) public view returns (address) {
        return ownerOf(tokenId);
    }

    function getBatchOwner(
        uint256 tokenId
    )
        public
        view
        batchExists(tokenId)
        returns (address)
    {
        return ownerOf(tokenId);
    }

    // ==========================================
    // 8. SOULBOUND: rekam medis tidak bisa dipindahkan
    // ==========================================

    function _update(
        address to,
        uint256 tokenId,
        address auth
    )
        internal
        override
        returns (address)
    {
        address from = _ownerOf(tokenId);

        // from == 0 berarti proses mint, selain itu transfer -> tolak.
        require(from == address(0), "Rekam medis tidak dapat dipindahkan");

        return super._update(to, tokenId, auth);
    }
}
